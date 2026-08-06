"""Structured logging.

SDD section 2.1 lists structured logs as cross-cutting. This module provides them
with two properties that matter for an indexing system.

Ambient context
    A single index build touches dozens of modules. Threading a repository and
    commit identifier through every function signature would be noise, and omitting
    them makes logs unusable at scale. Context variables carry them instead, set
    once at the top of a unit of work via :func:`log_context`, and injected into
    every record automatically. Context variables rather than thread locals so that
    the same mechanism keeps working when Milestone 2 introduces asynchronous
    workers.

Two renderings, one record
    ``human`` for development, ``json`` for production. The record's fields are
    identical either way; only the rendering differs, so a log line grepped in
    development corresponds field-for-field to what a log pipeline ingests.
"""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, Iterator, Mapping, Optional

from ria.config.settings import ObservabilitySettings

__all__ = [
    "configure_logging",
    "get_logger",
    "log_context",
    "current_log_context",
    "HumanFormatter",
    "JsonFormatter",
]

#: Ambient context merged into every emitted record.
_LOG_CONTEXT: ContextVar[Mapping[str, Any]] = ContextVar("ria_log_context", default={})

#: Record attributes created by :mod:`logging` itself, excluded when collecting
#: caller-supplied extras.
_RESERVED_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "stacklevel",
        "thread",
        "threadName",
        "taskName",
    }
)

#: Root logger name for this implementation. Kept distinct from the legacy
#: application's loggers so the two can be filtered independently.
_ROOT_LOGGER_NAME = "ria"


def current_log_context() -> Mapping[str, Any]:
    """Return the ambient log context for the current execution scope."""
    return _LOG_CONTEXT.get()


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    """Bind fields into the ambient log context for the duration of the block.

    Nested use merges rather than replaces, so an inner scope can add a file path
    without discarding the outer scope's repository identifier.

    Args:
        **fields: Values to merge into the context. ``None`` values are dropped so
            that an unset optional does not clutter every record.

    Yields:
        ``None``. The context is restored on exit, including on exception.
    """
    merged: Dict[str, Any] = dict(_LOG_CONTEXT.get())
    merged.update({key: value for key, value in fields.items() if value is not None})
    token: Token = _LOG_CONTEXT.set(merged)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def _collect_extras(record: logging.LogRecord) -> Dict[str, Any]:
    """Extract caller-supplied ``extra`` fields from a record.

    Args:
        record: Record being formatted.

    Returns:
        Fields the caller attached, excluding attributes ``logging`` created.
    """
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _RESERVED_ATTRIBUTES and not key.startswith("_")
    }


class HumanFormatter(logging.Formatter):
    """Single-line human-readable rendering for development.

    Format::

        2026-07-25T10:00:00Z INFO  ria.ingestion  message  key=value key=value
    """

    default_time_format = "%Y-%m-%dT%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        """Render a record as one human-readable line.

        Args:
            record: Record to render.

        Returns:
            The formatted line, with any exception traceback appended.
        """
        fields = dict(current_log_context())
        fields.update(_collect_extras(record))
        rendered = " ".join(f"{key}={fields[key]}" for key in sorted(fields))
        base = (
            f"{self.formatTime(record, self.default_time_format)}Z "
            f"{record.levelname:<8} {record.name} {record.getMessage()}"
        )
        line = f"{base}  {rendered}" if rendered else base
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


class JsonFormatter(logging.Formatter):
    """One JSON object per record, for production log pipelines.

    Values that are not JSON-serialisable are rendered with :func:`repr` rather
    than raising, because a logging call must never be the reason a build fails.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render a record as a single-line JSON object.

        Args:
            record: Record to render.

        Returns:
            A JSON document with stable top-level keys.
        """
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(current_log_context())
        payload.update(_collect_extras(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=repr, separators=(",", ":"))


def configure_logging(settings: ObservabilitySettings) -> None:
    """Configure the ``ria`` logger hierarchy.

    Idempotent: calling it again replaces the handler rather than adding a second
    one, which prevents the duplicated output that repeated configuration
    otherwise produces in test suites and reloading servers.

    Only the ``ria`` logger is configured, never the root logger. Reconfiguring
    the root logger would change the behaviour of the legacy application and of
    third-party libraries, which is not this module's business.

    Args:
        settings: Logging configuration.
    """
    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        JsonFormatter() if settings.log_format == "json" else HumanFormatter()
    )
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    # Records are fully handled here; propagating would duplicate them into any
    # root handler the host application installed.
    logger.propagate = False


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger within the ``ria`` hierarchy.

    Args:
        name: Dotted module name, conventionally ``__name__``. A name already
            inside the ``ria`` hierarchy is used as given; anything else is
            nested beneath it so that a stray name cannot escape the hierarchy's
            configuration.

    Returns:
        The logger.
    """
    if not name or name == _ROOT_LOGGER_NAME:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    if name.startswith(_ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")
