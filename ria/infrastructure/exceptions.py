"""Infrastructure Exceptions for RIA."""


class InfrastructureError(Exception):
    """Base exception for all infrastructure adapter failures."""

    pass


class GitCommandError(InfrastructureError):
    """Raised when a Git command subprocess fails."""

    pass


class WorkspaceError(InfrastructureError):
    """Raised when filesystem workspace allocation or cleanup fails."""

    pass


class DatabaseError(InfrastructureError):
    """Raised when SQLite database persistence or transaction fails."""

    pass


class FilesystemError(InfrastructureError):
    """Raised when low-level filesystem I/O operations fail."""

    pass


class ConfigurationError(InfrastructureError):
    """Raised when application settings or environment variables are invalid."""

    pass
