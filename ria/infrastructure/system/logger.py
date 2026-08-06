"""Standard Logging Adapter implementing LoggerPort."""

import logging
from typing import Any

from ria.ports.common.logger import LogContextValue, LoggerPort


class StandardLoggerAdapter(LoggerPort):
    """Standard Python logging adapter with context formatting."""

    def __init__(self, logger_name: str = "ria") -> None:
        self._logger = logging.getLogger(logger_name)

    def _format_context(self, message: str, context: dict[str, LogContextValue]) -> str:
        if not context:
            return message
        kv_pairs = " ".join(f"{k}={v}" for k, v in context.items())
        return f"{message} [{kv_pairs}]"

    def debug(self, message: str, **context: LogContextValue) -> None:
        self._logger.debug(self._format_context(message, context))

    def info(self, message: str, **context: LogContextValue) -> None:
        self._logger.info(self._format_context(message, context))

    def warning(self, message: str, **context: LogContextValue) -> None:
        self._logger.warning(self._format_context(message, context))

    def error(self, message: str, exc: Exception | None = None, **context: LogContextValue) -> None:
        self._logger.error(self._format_context(message, context), exc_info=exc)
