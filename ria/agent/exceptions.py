"""Application Exceptions for Agent Runtime Subsystem."""


class AgentException(Exception):
    """Base exception for Agent Runtime errors."""

    pass


class TaskSchedulerException(AgentException):
    """Raised when task scheduling fails."""

    pass


class ToolNotFoundException(AgentException):
    """Raised when target tool is not registered."""

    pass


class CheckpointNotFoundException(AgentException):
    """Raised when requested checkpoint does not exist."""

    pass
