"""Application Exceptions for Incremental Indexing Subsystem."""


class IncrementalException(Exception):
    """Base exception for Incremental Subsystem failures."""

    pass


class DiffException(IncrementalException):
    """Raised when Git diff computation fails."""

    pass


class SnapshotStorageException(IncrementalException):
    """Raised when snapshot persistence or retrieval fails."""

    pass


class IncrementalExecutionException(IncrementalException):
    """Raised when incremental reindexing execution fails."""

    pass
