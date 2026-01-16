"""Abstract storage backend interface."""

from abc import ABC, abstractmethod
from typing import BinaryIO, Iterator
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FileInfo:
    """File metadata returned by storage backend operations."""

    path: str
    name: str
    size: int  # Original/plaintext size
    is_directory: bool
    modified_at: datetime
    content_type: str | None = None
    # Encryption metadata (ADR 010)
    encrypted_size: int | None = None  # Size on disk including encryption overhead
    encryption_method: str = "none"  # none, server, server-user, client
    encryption_key_id: str | None = None  # Key ID for rotation tracking


class AbstractStorageBackend(ABC):
    """
    Abstract interface for storage backends.

    All paths are relative to the storage root and should not contain leading slashes.
    Example: "user123/documents/file.txt" not "/user123/documents/file.txt"
    """

    @abstractmethod
    def save(self, path: str, content: BinaryIO) -> FileInfo:
        """
        Save file content to path. Overwrites if exists.

        Args:
            path: Relative path where file should be saved
            content: File-like object containing the data

        Returns:
            FileInfo object with file metadata

        Raises:
            FileNotFoundError: If parent directory doesn't exist
            IsADirectoryError: If path points to an existing directory
        """
        pass

    @abstractmethod
    def open(self, path: str) -> BinaryIO:
        """
        Open file for reading.

        Args:
            path: Relative path to file

        Returns:
            File-like object in binary read mode

        Raises:
            FileNotFoundError: If file doesn't exist
            IsADirectoryError: If path points to a directory
        """
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """
        Delete file or empty directory at path.

        Args:
            path: Relative path to file or directory

        Raises:
            FileNotFoundError: If path doesn't exist
            OSError: If directory is not empty
        """
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """
        Check if path exists.

        Args:
            path: Relative path to check

        Returns:
            True if path exists, False otherwise
        """
        pass

    @abstractmethod
    def list(
        self, path: str = "", glob_pattern: str | None = None
    ) -> Iterator[FileInfo]:
        """
        List contents of directory.

        Args:
            path: Relative path to directory (empty string for root)
            glob_pattern: Optional glob pattern to filter results (e.g., "*.txt")

        Yields:
            FileInfo objects for each entry

        Raises:
            FileNotFoundError: If directory doesn't exist
            NotADirectoryError: If path points to a file
        """
        pass

    @abstractmethod
    def info(self, path: str) -> FileInfo:
        """
        Get metadata about a file or directory.

        Args:
            path: Relative path to file or directory

        Returns:
            FileInfo object with metadata

        Raises:
            FileNotFoundError: If path doesn't exist
        """
        pass

    @abstractmethod
    def mkdir(self, path: str) -> FileInfo:
        """
        Create directory. Parent directories created as needed.

        Args:
            path: Relative path to directory

        Returns:
            FileInfo object for the created directory
        """
        pass

    @abstractmethod
    def move(self, source: str, destination: str) -> FileInfo:
        """
        Move file or directory to new location.

        Args:
            source: Relative path to source file/directory
            destination: Relative path to destination directory

        Returns:
            FileInfo object for the moved file/directory at new location

        Raises:
            FileNotFoundError: If source doesn't exist
            FileExistsError: If file with same name exists at destination
            NotADirectoryError: If destination is not a directory
        """
        pass

    @abstractmethod
    def copy(
        self, source: str, destination: str, new_name: str | None = None
    ) -> FileInfo:
        """
        Copy file or directory to new location.

        Args:
            source: Relative path to source file/directory
            destination: Relative path to destination directory
            new_name: Optional new name for copied item (handles collisions)

        Returns:
            FileInfo object for the copied file/directory

        Raises:
            FileNotFoundError: If source doesn't exist
            NotADirectoryError: If destination is not a directory
        """
        pass
