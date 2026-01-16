"""Core utility functions for Storm Cloud."""

import re


class PathValidationError(Exception):
    """Raised when path contains invalid characters or traversal attempts."""

    pass


def normalize_path(path: str) -> str:
    """
    Normalize a storage path.

    - Strips leading/trailing slashes
    - Collapses multiple slashes
    - Blocks path traversal
    - Rejects invalid characters

    Args:
        path: Path to normalize

    Returns:
        Normalized path string

    Raises:
        PathValidationError: For invalid paths
    """
    if not path:
        return ""

    # Block null bytes and control characters
    if "\x00" in path or re.search(r"[\x00-\x1f]", path):
        raise PathValidationError("Path contains invalid characters")

    # Normalize slashes
    path = re.sub(r"/+", "/", path)
    path = path.strip("/")

    # Block path traversal
    parts = path.split("/")
    if ".." in parts:
        raise PathValidationError("Path traversal not allowed")

    return path


def validate_filename(name: str) -> str:
    """
    Validate a single filename component.

    Args:
        name: Filename to validate

    Returns:
        The validated filename

    Raises:
        PathValidationError: For invalid filenames
    """
    if not name:
        raise PathValidationError("Filename cannot be empty")

    if "/" in name or "\\" in name:
        raise PathValidationError("Filename cannot contain slashes")

    if name in (".", ".."):
        raise PathValidationError("Invalid filename")

    # Check for null bytes and control characters
    if "\x00" in name or re.search(r"[\x00-\x1f]", name):
        raise PathValidationError("Filename contains invalid characters")

    return name
