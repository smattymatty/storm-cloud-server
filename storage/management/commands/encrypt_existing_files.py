"""
Management command to encrypt existing unencrypted files.

Implements ADR 010: Server-Side Encryption.

Usage:
    # Audit mode - report unencrypted files
    python manage.py encrypt_existing_files --mode audit

    # Preview encryption without applying
    python manage.py encrypt_existing_files --mode encrypt --dry-run

    # Encrypt all unencrypted files
    python manage.py encrypt_existing_files --mode encrypt --force

    # Encrypt specific user's files
    python manage.py encrypt_existing_files --mode encrypt --user-id 1 --force
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.services.encryption import DecryptionError, EncryptionService
from core.storage.local import LocalStorageBackend
from storage.models import StoredFile

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = (
        "Encrypt existing unencrypted files (ADR 010). "
        "Use --mode audit to report, --mode encrypt --force to encrypt."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=str,
            choices=["audit", "encrypt"],
            default="audit",
            help="Mode: audit (report only) or encrypt (apply encryption)",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Target specific user only (default: all users)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying them",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required for encrypt mode (prevents accidental modification)",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        user_id = options.get("user_id")
        dry_run = options["dry_run"]
        force = options["force"]
        verbosity = options["verbosity"]

        # Initialize services
        self.backend = LocalStorageBackend()
        self.encryption = EncryptionService()

        # Validate encryption is enabled
        if not self.encryption.is_enabled:
            raise CommandError(
                "Encryption is not enabled. "
                "Set STORAGE_ENCRYPTION_METHOD and STORAGE_ENCRYPTION_KEY in settings."
            )

        # Validate force requirement for encrypt mode
        if mode == "encrypt" and not force and not dry_run:
            raise CommandError(
                "Mode 'encrypt' requires --force flag (or --dry-run for preview)"
            )

        # Header
        if verbosity >= 1:
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("Encrypt Existing Files"))
            self.stdout.write(self.style.SUCCESS("ADR 010: Server-Side Encryption"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write("")
            self.stdout.write(f"Mode: {mode}")
            self.stdout.write(f"Encryption method: {self.encryption.method}")
            self.stdout.write(f"Key ID: {self.encryption.key_id}")
            if user_id:
                self.stdout.write(f"User ID: {user_id}")
            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN: No changes will be made")
                )
            self.stdout.write("")

        # Get users to process
        if user_id:
            users = User.objects.filter(id=user_id)
            if not users.exists():
                raise CommandError(f"User with ID {user_id} not found")
        else:
            users = User.objects.all()

        # Statistics
        stats = {
            "users_scanned": 0,
            "files_scanned": 0,
            "already_encrypted": 0,
            "unencrypted": 0,
            "encrypted": 0,
            "errors": 0,
        }

        # Process each user
        for user in users:
            stats["users_scanned"] += 1
            self._process_user(user, mode, dry_run, verbosity, stats)

        # Summary
        self._display_summary(stats, mode, dry_run, verbosity)

    def _process_user(
        self, user, mode: str, dry_run: bool, verbosity: int, stats: dict
    ):
        """Process all files for a single user."""
        user_prefix = str(user.account.id)

        # Get all non-directory files for this user
        files = StoredFile.objects.filter(owner=user.account, is_directory=False)

        for stored_file in files:
            stats["files_scanned"] += 1
            full_path = f"{user_prefix}/{stored_file.path}"

            try:
                # Check current encryption status
                if stored_file.encryption_method != StoredFile.ENCRYPTION_NONE:
                    stats["already_encrypted"] += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            f"  [SKIP] {stored_file.path} (already encrypted)"
                        )
                    continue

                # Verify file exists and check actual encryption
                try:
                    raw_handle = self.backend.open_raw(full_path)
                    header = raw_handle.read(32)
                    raw_handle.close()
                except FileNotFoundError:
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  [SKIP] {stored_file.path} (file not found)"
                            )
                        )
                    continue

                # Check if file is actually encrypted on disk (DB might be out of sync)
                detected = self.encryption.detect_encryption(header)
                if detected != "none":
                    stats["already_encrypted"] += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            f"  [SKIP] {stored_file.path} (encrypted on disk, updating DB)"
                        )
                    # Update DB to reflect actual state
                    if not dry_run:
                        self._update_db_encryption_state(stored_file, full_path)
                    continue

                # File is unencrypted
                stats["unencrypted"] += 1

                if mode == "audit":
                    if verbosity >= 1:
                        self.stdout.write(f"  [UNENCRYPTED] {stored_file.path}")
                    continue

                # Encrypt mode
                if verbosity >= 1:
                    action = "Would encrypt" if dry_run else "Encrypting"
                    self.stdout.write(f"  [{action}] {stored_file.path}")

                if not dry_run:
                    self._encrypt_file(stored_file, full_path)
                    stats["encrypted"] += 1

            except Exception as e:
                stats["errors"] += 1
                self.stdout.write(
                    self.style.ERROR(f"  [ERROR] {stored_file.path}: {e}")
                )
                logger.exception(f"Error processing {stored_file.path}")

    def _encrypt_file(self, stored_file: StoredFile, full_path: str):
        """Encrypt a single file in place."""
        # Read plaintext
        raw_handle = self.backend.open_raw(full_path)
        plaintext = raw_handle.read()
        raw_handle.close()

        original_size = len(plaintext)

        # Encrypt
        encrypted = self.encryption.encrypt_file(plaintext)
        encrypted_size = len(encrypted)

        # Write encrypted content back
        # Use the backend's internal path resolution
        from pathlib import Path

        storage_root = self.backend.storage_root
        file_path = storage_root / full_path
        file_path.write_bytes(encrypted)

        # Update database record
        stored_file.size = original_size
        stored_file.encrypted_size = encrypted_size
        stored_file.encryption_method = StoredFile.ENCRYPTION_SERVER
        stored_file.key_id = self.encryption.key_id
        stored_file.save(
            update_fields=[
                "size",
                "encrypted_size",
                "encryption_method",
                "key_id",
                "updated_at",
            ]
        )

    def _update_db_encryption_state(self, stored_file: StoredFile, full_path: str):
        """Update DB record to reflect actual encryption state on disk."""
        try:
            # Read and decrypt to get original size
            raw_handle = self.backend.open_raw(full_path)
            encrypted_data = raw_handle.read()
            raw_handle.close()

            encrypted_size = len(encrypted_data)

            try:
                plaintext = self.encryption.decrypt_file(encrypted_data)
                original_size = len(plaintext)
            except DecryptionError:
                # Can't decrypt, use on-disk size
                original_size = encrypted_size
                encrypted_size = None

            stored_file.size = original_size
            stored_file.encrypted_size = encrypted_size
            stored_file.encryption_method = StoredFile.ENCRYPTION_SERVER
            stored_file.key_id = self.encryption.key_id
            stored_file.save(
                update_fields=[
                    "size",
                    "encrypted_size",
                    "encryption_method",
                    "key_id",
                    "updated_at",
                ]
            )
        except Exception as e:
            logger.error(f"Error updating encryption state for {stored_file.path}: {e}")

    def _display_summary(self, stats: dict, mode: str, dry_run: bool, verbosity: int):
        """Display summary statistics."""
        if verbosity < 1:
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Summary"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"Users scanned: {stats['users_scanned']}")
        self.stdout.write(f"Files scanned: {stats['files_scanned']}")
        self.stdout.write(f"Already encrypted: {stats['already_encrypted']}")
        self.stdout.write(f"Unencrypted files: {stats['unencrypted']}")

        if mode == "encrypt":
            if dry_run:
                self.stdout.write(f"Would encrypt: {stats['unencrypted']}")
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Files encrypted: {stats['encrypted']}")
                )

        if stats["errors"] > 0:
            self.stdout.write(self.style.ERROR(f"Errors: {stats['errors']}"))

        self.stdout.write("")

        # Final status
        if mode == "audit":
            if stats["unencrypted"] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"Found {stats['unencrypted']} unencrypted file(s). "
                        "Run with --mode encrypt --force to encrypt them."
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS("All files are encrypted."))
        elif dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run complete. Run with --force to apply changes."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Encryption complete."))
