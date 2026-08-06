"""Domain Exceptions for C5 Snapshot & Incremental Subsystem."""


class SnapshotDomainException(Exception):
    """Base exception for all domain errors in Snapshot and Incremental Subsystem."""

    pass


class InvalidSnapshotError(SnapshotDomainException):
    """Raised when a repository snapshot is ill-formed."""

    pass


class IncrementalPlanningError(SnapshotDomainException):
    """Raised when incremental plan construction fails."""

    pass
