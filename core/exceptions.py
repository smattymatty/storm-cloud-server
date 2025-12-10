"""Custom exceptions for Storm Cloud."""


class StormCloudException(Exception):
    """Base exception for Storm Cloud errors."""
    pass


class StorageError(StormCloudException):
    """Storage backend error."""
    pass


class IndexDesyncError(StormCloudException):
    """Database and filesystem are out of sync."""
    pass


class ValidationError(StormCloudException):
    """Request validation error."""
    pass
