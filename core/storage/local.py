"""Local filesystem storage backend."""

from pathlib import Path
from typing import BinaryIO, Iterator
from datetime import datetime
import mimetypes
from fnmatch import fnmatch

from django.conf import settings

from .base import AbstractStorageBackend, FileInfo


class LocalStorageBackend(AbstractStorageBackend):
    """
    Local filesystem storage backend.

    Stores files under STORMCLOUD_STORAGE_ROOT directory.
    All paths are relative to this root.
    """

    def __init__(self, storage_root: Path | None = None):
        """
        Initialize local storage backend.

        Args:
            storage_root: Optional override for storage root path.
                         Defaults to settings.STORMCLOUD_STORAGE_ROOT
        """
        self.storage_root = storage_root or settings.STORMCLOUD_STORAGE_ROOT
        self.storage_root = Path(self.storage_root)

        # Ensure storage root exists
        self.storage_root.mkdir(parents=True, exist_ok=True)

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
        path = path.lstrip('/')

        # Resolve to absolute path
        full_path = (self.storage_root / path).resolve()

        # Security check: ensure resolved path is within storage root
        try:
            full_path.relative_to(self.storage_root)
        except ValueError:
            raise ValueError(f"Invalid path: {path} (directory traversal detected)")

        return full_path

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
            content_type=mimetypes.guess_type(path.name)[0] if path.is_file() else None
        )

    def save(self, path: str, content: BinaryIO) -> FileInfo:
        """Save file content to path."""
        full_path = self._resolve_path(path)

        # Check if path is a directory
        if full_path.exists() and full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        # Ensure parent directory exists
        if not full_path.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {path}")

        # Write file
        with full_path.open('wb') as f:
            for chunk in iter(lambda: content.read(8192), b''):
                f.write(chunk)

        return self._file_info(full_path, path)

    def open(self, path: str) -> BinaryIO:
        """Open file for reading."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if full_path.is_dir():
            raise IsADirectoryError(f"Path is a directory: {path}")

        return full_path.open('rb')

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

    def list(self, path: str = "", glob_pattern: str | None = None) -> Iterator[FileInfo]:
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

    def copy(self, source: str, destination: str, new_name: str | None = None) -> FileInfo:
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
