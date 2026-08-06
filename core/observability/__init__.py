"""Observability Core Package.

Interface-agnostic observability infrastructure for logging, metrics,
request correlation, sensitive data redaction, and performance timing.
Reusable across REST API, MCP Server, CLI commands, and background workers.
"""

from core.observability.redaction import RedactionFilter, sanitize_sensitive_data
from core.observability.context import (
    request_id_var,
    build_id_var,
    repository_var,
    analysis_var,
    RequestContext,
    get_current_request_id,
)
from core.observability.metrics import MetricsCollector, metrics_collector
from core.observability.timing import time_operation

__all__ = [
    "RedactionFilter",
    "sanitize_sensitive_data",
    "request_id_var",
    "build_id_var",
    "repository_var",
    "analysis_var",
    "RequestContext",
    "get_current_request_id",
    "MetricsCollector",
    "metrics_collector",
    "time_operation",
]
