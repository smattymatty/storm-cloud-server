"""
Management command to rebuild storage index from filesystem.

Implements ADR 000: "Index rebuild, filesystem wins"
"""

from django.core.management.base import BaseCommand, CommandError
from storage.tasks import rebuild_storage_index


class Command(BaseCommand):
    help = (
        "Rebuild storage index from filesystem (ADR 000/009: Filesystem wins). "
        "Clean mode will CASCADE delete related ShareLinks automatically."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=str,
            choices=["audit", "sync", "clean", "full"],
            default="audit",
            help=(
                "Sync mode: audit (report only), sync (add missing), "
                "clean (delete orphaned + CASCADE ShareLinks), full (sync+clean)"
            ),
        )
        parser.add_argument(
            "--user-id", type=int, help="Sync specific user only (default: all users)"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying them",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required for clean and full modes (prevents accidental deletion)",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        user_id = options.get("user_id")
        dry_run = options["dry_run"]
        force = options["force"]
        verbosity = options["verbosity"]

        # Validate force requirement
        if mode in ["clean", "full"] and not force:
            raise CommandError(
                f"Mode '{mode}' requires --force flag to prevent accidental data loss"
            )

        # Header
        if verbosity >= 1:
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("Storage Index Rebuild"))
            self.stdout.write(self.style.SUCCESS("ADR 000: Filesystem wins policy"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write("")
            self.stdout.write(f"Mode: {mode}")
            if user_id:
                self.stdout.write(f"User ID: {user_id}")
            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN: No changes will be made")
                )
            self.stdout.write("")

        # Enqueue task (ImmediateBackend runs synchronously)
        result = rebuild_storage_index.enqueue(
            mode=mode,
            user_id=user_id,
            dry_run=dry_run,
            force=force,
        )

        # Get stats from result
        if result.status == "SUCCESSFUL":
            stats = result.return_value

            # Display results
            if verbosity >= 1:
                self._display_stats(stats, verbosity)
        else:
            # Task failed
            self.stdout.write(self.style.ERROR("✗ Task failed!"))
            if result.errors:
                for error in result.errors:
                    self.stdout.write(self.style.ERROR(f"\n{error.traceback}"))
            raise CommandError("Index rebuild failed")

    def _display_stats(self, stats, verbosity):
        """Display sync statistics."""
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Results"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # Summary
        self.stdout.write(f"Users scanned: {stats['users_scanned']}")
        self.stdout.write(f"Files on disk: {stats['files_on_disk']}")
        self.stdout.write(f"Files in DB: {stats['files_in_db']}")
        self.stdout.write("")

        # Discrepancies
        if stats["missing_in_db"] > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠ Missing in DB: {stats['missing_in_db']}")
            )
        if stats["orphaned_in_db"] > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠ Orphaned in DB: {stats['orphaned_in_db']}")
            )

        # Actions taken
        if stats["records_created"] > 0:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Records created: {stats['records_created']}")
            )
        if stats["records_deleted"] > 0:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Records deleted: {stats['records_deleted']}")
            )
        if stats["records_skipped"] > 0:
            self.stdout.write(
                self.style.WARNING(f"⊘ Records skipped: {stats['records_skipped']}")
            )

        # Errors
        if stats["errors"]:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"Errors ({len(stats['errors'])}):"))
            for error in stats["errors"][:10]:  # Show first 10
                self.stdout.write(self.style.ERROR(f"  • {error}"))
            if len(stats["errors"]) > 10:
                self.stdout.write(
                    self.style.ERROR(f"  ... and {len(stats['errors']) - 10} more")
                )

        self.stdout.write("")

        # Success message
        if (
            stats["records_created"] == 0
            and stats["records_deleted"] == 0
            and not stats["errors"]
        ):
            self.stdout.write(self.style.SUCCESS("✓ Index is in sync!"))
