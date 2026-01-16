"""Storage backend abstraction for Storm Cloud."""

from .base import AbstractStorageBackend, FileInfo
from .local import LocalStorageBackend

__all__ = ["AbstractStorageBackend", "FileInfo", "LocalStorageBackend"]
