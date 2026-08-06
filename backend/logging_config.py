"""Logging configurations for human-readable and structured JSON logs."""

import json
import logging
from datetime import datetime
from typing import Any, Dict

from core.logging_context import (
    analysis_var,
    build_id_var,
    repository_var,
    request_id_var,
)
from core.observability.redaction import RedactionFilter, sanitize_sensitive_data


class JsonFormatter(logging.Formatter):
    """Formats log records as structured JSON with automatic sensitive data redaction."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_var.get()
        b_id = build_id_var.get()
        repo = repository_var.get()
        analysis = analysis_var.get()

        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_sensitive_data(record.getMessage()),
        }

        # Add trace contexts if available
        if req_id:
            log_data["request_id"] = req_id
        if b_id:
            log_data["build_id"] = b_id
        if repo:
            log_data["repository"] = repo
        if analysis:
            log_data["analysis"] = analysis

        # Inject extra attributes
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "error_details"):
            log_data["error_details"] = sanitize_sensitive_data(record.error_details)

        # Include exception tracebacks
        if record.exc_info:
            log_data["exception"] = sanitize_sensitive_data(self.formatException(record.exc_info))

        return json.dumps(log_data)


class HumanFormatter(logging.Formatter):
    """Formats log records in a developer-friendly human readable format with sensitive data redaction."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_var.get()
        b_id = build_id_var.get()
        repo = repository_var.get()
        analysis = analysis_var.get()

        # Timestamp and level
        timestamp = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S,%f"
        )[:-3]
        parts = [
            f"{timestamp}",
            f"[{record.levelname}]",
            f"[{record.name}]",
        ]

        # Context details
        ctx = []
        if req_id:
            ctx.append(f"req={req_id}")
        if b_id:
            ctx.append(f"build={b_id}")
        if repo:
            ctx.append(f"repo={repo}")
        if analysis:
            ctx.append(f"analysis={analysis}")

        if ctx:
            parts.append(f"({', '.join(ctx)})")

        parts.append("-")
        parts.append(sanitize_sensitive_data(record.getMessage()))

        if hasattr(record, "duration_ms"):
            parts.append(f"duration={record.duration_ms:.2f}ms")

        res = " ".join(parts)

        # Include traceback
        if record.exc_info:
            res += "\n" + sanitize_sensitive_data(self.formatException(record.exc_info))

        return res


def configure_logging(log_level: str = "INFO", log_format: str = "human") -> None:
    """Configures the root logging logger with RedactionFilter and specified formatters."""
    root = logging.getLogger()

    # Clear existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    # Set up console handler
    handler = logging.StreamHandler()
    if log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(HumanFormatter())

    # Add RedactionFilter to handler and root logger
    redaction_filter = RedactionFilter()
    handler.addFilter(redaction_filter)
    root.addFilter(redaction_filter)

    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
