"""Local filesystem storage backend."""

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterator
from datetime import datetime
import mimetypes
from fnmatch import fnmatch

from django.conf import settings

from .base import AbstractStorageBackend, FileInfo
from core.services.encryption import EncryptionService


class LocalStorageBackend(AbstractStorageBackend):
    """
    Local filesystem storage backend.

    Stores files under two directories:
    - STORMCLOUD_STORAGE_ROOT: Private user files (storage_root/{account_id}/...)
    - STORMCLOUD_SHARED_STORAGE_ROOT: Shared org files (shared_root/{org_id}/...)
    """

    def __init__(
        self,
        storage_root: Path | None = None,
        shared_root: Path | None = None,
    ):
        """
        Initialize local storage backend.

        Args:
            storage_root: Optional override for private storage root path.
                         Defaults to settings.STORMCLOUD_STORAGE_ROOT
            shared_root: Optional override for shared storage root path.
                         Defaults to settings.STORMCLOUD_SHARED_STORAGE_ROOT
        """
        self.storage_root = storage_root or settings.STORMCLOUD_STORAGE_ROOT
        self.storage_root = Path(self.storage_root)

        self.shared_root = shared_root or settings.STORMCLOUD_SHARED_STORAGE_ROOT
        self.shared_root = Path(self.shared_root)

        # Ensure storage roots exist
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.shared_root.mkdir(parents=True, exist_ok=True)

        # Encryption service (ADR 010)
        self.encryption = EncryptionService()

    def _resolve_path(self, path: str) -> Path:
        """
        Convert relative path to absolute filesystem path.

        Args:
            path: Relative path (e.g., "user123/file.txt")

        Returns:
            Absolute Path object

        Raises:
            ValueError: If path attempts directory traversal
        """
        # Strip leading slashes if present
        path = path.lstrip("/")

        # Resolve to absolute path
        full_path = (self.storage_root / path).resolve()

        # Security check: ensure resolved path is within storage root
        try:
            full_path.relative_to(self.storage_root)
        except ValueError:
            raise ValueError(f"Invalid path: {path} (directory traversal detected)")

        return full_path

    def _resolve_shared_path(self, org_id: str | int, path: str) -> Path:
        """
        Convert relative path to absolute filesystem path in shared storage.

        Args:
            org_id: Organization ID
            path: Relative path within org's shared storage (e.g., "docs/file.txt")

        Returns:
            Absolute Path object

        Raises:
            ValueError: If path attempts directory traversal
        """
        # Strip leading slashes if present
        path = path.lstrip("/") if path else ""

        # Org's shared storage root
        org_root = self.shared_root / str(org_id)

        # Resolve to absolute path
        if path:
            full_path = (org_root / path).resolve()
        else:
            full_path = org_root.resolve()

        # Security check: ensure resolved path is within org's shared root
        try:
            full_path.relative_to(org_root)
        except ValueError:
            raise ValueError(f"Invalid path: {path} (directory traversal detected)")

        return full_path

    def get_org_storage_root(self, org_id: str | int) -> Path:
        """
        Get the storage root directory for an organization's shared files.

        Args:
            org_id: Organization ID

        Returns:
            Path to org's shared storage root (creates if doesn't exist)
        """
        org_root = self.shared_root / str(org_id)
        org_root.mkdir(parents=True, exist_ok=True)
        return org_root

    def _shared_file_info(
        self, path: Path, relative_path: str, org_id: str | int
    ) -> FileInfo:
        """
        Create FileInfo from filesystem path in shared storage.

        Args:
            path: Absolute filesystem Path
            relative_path: Relative path for FileInfo
            org_id: Organization ID (for context)

        Returns:
            FileInfo object
        """
        stat = path.stat()

        return FileInfo(
            path=relative_path,
            name=path.name,
            size=stat.st_size if path.is_file() else 0,
            is_directory=path.is_dir(),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            content_type=mimetypes.guess_type(path.name)[0] if path.is_file() else None,
        )

    # ==========================================================================
    # Shared Storage Operations
    # ==========================================================================

    def save_shared(self, org_id: str | int, path: str, content: BinaryIO) -> FileInfo:
        """Save file content to shared storage path with encryption if enabled."""
        full_path = self._resolve_shared_path(org_id, path)

        # Check if path is a directory
        if full_path.exists() and full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        # Ensure parent directory exists
        if not full_path.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {path}")

        # Read all content for encryption
        plaintext = content.read()
        original_size = len(plaintext)

        # Encrypt content (returns unchanged if encryption disabled)
        encrypted = self.encryption.encrypt_file(plaintext)

        # Write encrypted content
        full_path.write_bytes(encrypted)

        stat = full_path.stat()
        return FileInfo(
            path=path,
            name=full_path.name,
            size=original_size,
            is_directory=False,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            content_type=mimetypes.guess_type(full_path.name)[0],
            encrypted_size=len(encrypted) if self.encryption.is_enabled else None,
            encryption_method=self.encryption.method,
            encryption_key_id=self.encryption.key_id,
        )

    def open_shared(self, org_id: str | int, path: str) -> BinaryIO:
        """Open shared file for reading, decrypting if needed."""
        full_path = self._resolve_shared_path(org_id, path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        # Read encrypted content and decrypt
        encrypted = full_path.read_bytes()
        plaintext = self.encryption.decrypt_file(encrypted)

        return BytesIO(plaintext)

    def open_raw_shared(self, org_id: str | int, path: str) -> BinaryIO:
        """Open shared file without decryption (for migration, debugging)."""
        full_path = self._resolve_shared_path(org_id, path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        return full_path.open("rb")

    def delete_shared(self, org_id: str | int, path: str) -> None:
        """Delete shared file or empty directory."""
        full_path = self._resolve_shared_path(org_id, path)

        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        if full_path.is_dir():
            full_path.rmdir()
        else:
            full_path.unlink()

    def exists_shared(self, org_id: str | int, path: str) -> bool:
        """Check if shared path exists."""
        try:
            full_path = self._resolve_shared_path(org_id, path)
            return full_path.exists()
        except ValueError:
            return False

    def list_shared(
        self, org_id: str | int, path: str = "", glob_pattern: str | None = None
    ) -> Iterator[FileInfo]:
        """List contents of shared directory."""
        org_root = self.get_org_storage_root(org_id)
        full_path = self._resolve_shared_path(org_id, path) if path else org_root

        if not full_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not full_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        for entry in full_path.iterdir():
            # Calculate relative path from org's shared root
            relative_path = str(entry.relative_to(org_root))

            # Apply glob filter if provided
            if glob_pattern and not fnmatch(entry.name, glob_pattern):
                continue

            yield self._shared_file_info(entry, relative_path, org_id)

    def info_shared(self, org_id: str | int, path: str) -> FileInfo:
        """Get metadata about a shared file or directory."""
        full_path = self._resolve_shared_path(org_id, path)

        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        return self._shared_file_info(full_path, path, org_id)

    def mkdir_shared(self, org_id: str | int, path: str) -> FileInfo:
        """Create directory in shared storage with parents."""
        full_path = self._resolve_shared_path(org_id, path)
        full_path.mkdir(parents=True, exist_ok=True)
        return self._shared_file_info(full_path, path, org_id)

    def move_shared(self, org_id: str | int, source: str, destination: str) -> FileInfo:
        """Move shared file or directory to new location."""
        import shutil

        source_full = self._resolve_shared_path(org_id, source)
        dest_full = self._resolve_shared_path(org_id, destination)
        org_root = self.get_org_storage_root(org_id)

        if not source_full.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        if not dest_full.exists():
            raise FileNotFoundError(f"Destination directory not found: {destination}")

        if not dest_full.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {destination}")

        source_name = source_full.name
        new_full_path = dest_full / source_name

        if new_full_path.exists():
            raise FileExistsError(
                f"File '{source_name}' already exists at destination: {destination}"
            )

        shutil.move(str(source_full), str(new_full_path))
        new_relative_path = str(new_full_path.relative_to(org_root))

        return self._shared_file_info(new_full_path, new_relative_path, org_id)

    def copy_shared(
        self,
        org_id: str | int,
        source: str,
        destination: str,
        new_name: str | None = None,
    ) -> FileInfo:
        """Copy shared file or directory to new location."""
        import shutil

        source_full = self._resolve_shared_path(org_id, source)
        dest_full = self._resolve_shared_path(org_id, destination)
        org_root = self.get_org_storage_root(org_id)

        if not source_full.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        if not dest_full.exists():
            raise FileNotFoundError(f"Destination directory not found: {destination}")

        if not dest_full.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {destination}")

        # Determine final name (with collision handling)
        if new_name:
            final_name = new_name
        else:
            final_name = source_full.name
            new_full_path = dest_full / final_name

            if new_full_path.exists():
                base_name = source_full.stem
                extension = source_full.suffix
                counter = 1

                while new_full_path.exists():
                    if counter == 1:
                        final_name = f"{base_name} (copy){extension}"
                    else:
                        final_name = f"{base_name} (copy {counter}){extension}"
                    new_full_path = dest_full / final_name
                    counter += 1

        new_full_path = dest_full / final_name

        if source_full.is_dir():
            shutil.copytree(str(source_full), str(new_full_path))
        else:
            shutil.copy2(str(source_full), str(new_full_path))

        new_relative_path = str(new_full_path.relative_to(org_root))

        return self._shared_file_info(new_full_path, new_relative_path, org_id)

    def _file_info(self, path: Path, relative_path: str) -> FileInfo:
        """
        Create FileInfo from filesystem path.

        Args:
            path: Absolute filesystem Path
            relative_path: Relative path for FileInfo

        Returns:
            FileInfo object
        """
        stat = path.stat()

        return FileInfo(
            path=relative_path,
            name=path.name,
            size=stat.st_size if path.is_file() else 0,
            is_directory=path.is_dir(),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            content_type=mimetypes.guess_type(path.name)[0] if path.is_file() else None,
        )

    def save(self, path: str, content: BinaryIO) -> FileInfo:
        """Save file content to path with encryption if enabled."""
        full_path = self._resolve_path(path)

        # Check if path is a directory
        if full_path.exists() and full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        # Ensure parent directory exists
        if not full_path.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {path}")

        # Read all content for encryption
        plaintext = content.read()
        original_size = len(plaintext)

        # Encrypt content (returns unchanged if encryption disabled)
        encrypted = self.encryption.encrypt_file(plaintext)

        # Write encrypted content
        full_path.write_bytes(encrypted)

        stat = full_path.stat()
        return FileInfo(
            path=path,
            name=full_path.name,
            size=original_size,  # Original plaintext size
            is_directory=False,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            content_type=mimetypes.guess_type(full_path.name)[0],
            # Encryption metadata (ADR 010)
            encrypted_size=len(encrypted) if self.encryption.is_enabled else None,
            encryption_method=self.encryption.method,
            encryption_key_id=self.encryption.key_id,
        )

    def open(self, path: str) -> BinaryIO:
        """Open file for reading, decrypting if needed."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        # Read encrypted content and decrypt
        encrypted = full_path.read_bytes()
        plaintext = self.encryption.decrypt_file(encrypted)

        # Return as file-like object
        return BytesIO(plaintext)

    def open_raw(self, path: str) -> BinaryIO:
        """Open file without decryption (for migration, debugging)."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        return full_path.open("rb")

    def delete(self, path: str) -> None:
        """Delete file or empty directory."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        if full_path.is_dir():
            full_path.rmdir()  # Raises OSError if directory not empty
        else:
            full_path.unlink()

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        try:
            full_path = self._resolve_path(path)
            return full_path.exists()
        except ValueError:
            # Invalid path (traversal attempt)
            return False

    def list(
        self, path: str = "", glob_pattern: str | None = None
    ) -> Iterator[FileInfo]:
        """List contents of directory."""
        full_path = self._resolve_path(path) if path else self.storage_root

        if not full_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not full_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        for entry in full_path.iterdir():
            # Calculate relative path from storage root
            relative_path = str(entry.relative_to(self.storage_root))

            # Apply glob filter if provided
            if glob_pattern and not fnmatch(entry.name, glob_pattern):
                continue

            yield self._file_info(entry, relative_path)

    def info(self, path: str) -> FileInfo:
        """Get metadata about a file or directory."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        return self._file_info(full_path, path)

    def mkdir(self, path: str) -> FileInfo:
        """Create directory with parents."""
        full_path = self._resolve_path(path)
        full_path.mkdir(parents=True, exist_ok=True)
        return self._file_info(full_path, path)

    def move(self, source: str, destination: str) -> FileInfo:
        """Move file or directory to new location."""
        import shutil

        source_full = self._resolve_path(source)
        dest_full = self._resolve_path(destination)

        # Validate source exists
        if not source_full.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        # Validate destination is a directory
        if not dest_full.exists():
            raise FileNotFoundError(f"Destination directory not found: {destination}")

        if not dest_full.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {destination}")

        # Calculate new path
        source_name = source_full.name
        new_full_path = dest_full / source_name

        # Check for collision
        if new_full_path.exists():
            raise FileExistsError(
                f"File '{source_name}' already exists at destination: {destination}"
            )

        # Perform move
        shutil.move(str(source_full), str(new_full_path))

        # Calculate relative path for return value
        new_relative_path = str(new_full_path.relative_to(self.storage_root))

        return self._file_info(new_full_path, new_relative_path)

    def copy(
        self, source: str, destination: str, new_name: str | None = None
    ) -> FileInfo:
        """Copy file or directory to new location."""
        import shutil

        source_full = self._resolve_path(source)
        dest_full = self._resolve_path(destination)

        # Validate source exists
        if not source_full.exists():
            raise FileNotFoundError(f"Source not found: {source}")

        # Validate destination is a directory
        if not dest_full.exists():
            raise FileNotFoundError(f"Destination directory not found: {destination}")

        if not dest_full.is_dir():
            raise NotADirectoryError(f"Destination is not a directory: {destination}")

        # Determine final name (with collision handling)
        if new_name:
            final_name = new_name
        else:
            final_name = source_full.name
            new_full_path = dest_full / final_name

            # Handle name collisions by appending " (copy)", " (copy 2)", etc.
            if new_full_path.exists():
                base_name = source_full.stem
                extension = source_full.suffix
                counter = 1

                while new_full_path.exists():
                    if counter == 1:
                        final_name = f"{base_name} (copy){extension}"
                    else:
                        final_name = f"{base_name} (copy {counter}){extension}"
                    new_full_path = dest_full / final_name
                    counter += 1

        new_full_path = dest_full / final_name

        # Perform copy
        if source_full.is_dir():
            shutil.copytree(str(source_full), str(new_full_path))
        else:
            shutil.copy2(str(source_full), str(new_full_path))

        # Calculate relative path for return value
        new_relative_path = str(new_full_path.relative_to(self.storage_root))

        return self._file_info(new_full_path, new_relative_path)
