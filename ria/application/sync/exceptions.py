"""Application Exceptions for Repository Sync."""


class SyncApplicationException(Exception):
    """Base exception for all application-level errors in Repository Sync."""

    pass


class RepositorySyncException(SyncApplicationException):
    """Raised when repository clone, fetch, or checkout operation fails."""

    pass


class LockAcquisitionException(SyncApplicationException):
    """Raised when process lock cannot be acquired for repository synchronization."""

    pass
