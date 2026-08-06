"""Domain Exceptions for Agent Runtime Subsystem."""


class AgentDomainException(Exception):
    """Base exception for all domain errors in Agent Runtime."""

    pass


class InvalidGoalError(AgentDomainException):
    """Raised when a goal is malformed or invalid."""

    pass


class TaskExecutionError(AgentDomainException):
    """Raised when a task in the execution graph fails."""

    pass


class PlanningError(AgentDomainException):
    """Raised when plan generation fails."""

    pass


class CheckpointError(AgentDomainException):
    """Raised when checkpoint creation or restoration fails."""

    pass


class VerificationError(AgentDomainException):
    """Raised when execution verification fails."""

    pass
