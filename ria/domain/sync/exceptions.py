"""Domain Exceptions for C0 Repository Sync."""


class SyncDomainException(Exception):
    """Base exception for all domain errors in Repository Sync."""

    pass


class InvalidCommitRefError(SyncDomainException):
    """Raised when a commit SHA is ill-formed or invalid."""

    pass


class InvalidBranchRefError(SyncDomainException):
    """Raised when a branch reference is ill-formed or invalid."""

    pass


class RepositoryLockedError(SyncDomainException):
    """Raised when attempting an operation on a locked repository."""

    pass


class InvalidStateTransitionError(SyncDomainException):
    """Raised when an invalid state transition is attempted on RepositoryState."""

    pass
