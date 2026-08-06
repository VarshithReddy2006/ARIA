"""Logger Port abstraction for structured logging."""

from typing import Mapping, Protocol, Union, runtime_checkable

LogContextValue = Union[str, int, float, bool, None]


@runtime_checkable
class LoggerPort(Protocol):
    """Protocol for abstracting structured application logging.

    Preconditions: Message string must be non-empty. Key-value context values must be primitive JSON-serializable types.
    Postconditions: Structured log entry emitted without raising exceptions.
    """

    def debug(self, message: str, **context: LogContextValue) -> None:
        """Emit a debug level structured log message with optional key-value context."""
        ...

    def info(self, message: str, **context: LogContextValue) -> None:
        """Emit an info level structured log message with optional key-value context."""
        ...

    def warning(self, message: str, **context: LogContextValue) -> None:
        """Emit a warning level structured log message with optional key-value context."""
        ...

    def error(self, message: str, exc: Exception | None = None, **context: LogContextValue) -> None:
        """Emit an error level structured log message with optional exception and context."""
        ...
