"""RIA Infrastructure Adapters Layer."""

from ria.infrastructure.exceptions import (
    ConfigurationError,
    DatabaseError,
    FilesystemError,
    GitCommandError,
    InfrastructureError,
    WorkspaceError,
)
from ria.infrastructure.filesystem import OSFilesystemAdapter, WorkspaceManager
from ria.infrastructure.git import SubprocessGitAdapter
from ria.infrastructure.storage import SQLiteRepositoryLockAdapter, SQLiteRepositoryRegistryAdapter
from ria.infrastructure.system import (
    HashlibHashingAdapter,
    InMemoryMetricsAdapter,
    StandardLoggerAdapter,
    SystemClockAdapter,
)

__all__ = [
    # Infrastructure Exceptions
    "InfrastructureError",
    "GitCommandError",
    "WorkspaceError",
    "DatabaseError",
    "FilesystemError",
    "ConfigurationError",
    # Adapters
    "SystemClockAdapter",
    "HashlibHashingAdapter",
    "StandardLoggerAdapter",
    "InMemoryMetricsAdapter",
    "OSFilesystemAdapter",
    "WorkspaceManager",
    "SQLiteRepositoryRegistryAdapter",
    "SQLiteRepositoryLockAdapter",
    "SubprocessGitAdapter",
]
