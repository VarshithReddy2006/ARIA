"""Observability — cross-cutting, not an infrastructure adapter.

SDD section 2.1 lists observability as cross-cutting across every layer, and that
placement is deliberate rather than cosmetic. Logging is emitted from the
application layer, which SDD section 2.3 forbids from importing infrastructure. If
this package sat under ``ria.infrastructure``, every use case that logs would
violate the dependency rule.

Two different mechanisms, for two different reasons
--------------------------------------------------
Logging is used directly
    It depends only on the standard library, has no substitutable backend worth
    abstracting, and needs no test double: a test asserts on captured records.
    Introducing a logging port would be an abstraction with exactly one
    implementation, which the build brief forbids.
Metrics goes through a port
    Measurements are emitted from the application layer and must be assertable and
    disableable, and a real deployment eventually needs a different backend. That
    is a genuine substitution boundary, so :class:`~ria.ports.metrics.MetricsSink`
    exists and the implementations here satisfy it.

Contents
--------
``logging``
    Structured logging with ambient context and two renderings.
``metrics``
    In-memory and null :class:`~ria.ports.metrics.MetricsSink` implementations.
"""

from __future__ import annotations

from ria.observability.logging import (
    HumanFormatter,
    JsonFormatter,
    configure_logging,
    current_log_context,
    get_logger,
    log_context,
)
from ria.observability.metrics import (
    Distribution,
    InMemoryMetricsSink,
    MetricKey,
    NullMetricsSink,
)

__all__ = [
    "Distribution",
    "HumanFormatter",
    "InMemoryMetricsSink",
    "JsonFormatter",
    "MetricKey",
    "NullMetricsSink",
    "configure_logging",
    "current_log_context",
    "get_logger",
    "log_context",
]
