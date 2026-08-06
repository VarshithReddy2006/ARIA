"""Metrics port.

SDD section 2.1 lists observability as cross-cutting across every layer, and the
build brief requires metrics on every unit of work. This port is how the domain
and application layers emit measurements without importing a metrics backend,
which would invert the dependency rule of SDD section 2.3.

Metric naming convention
------------------------
``ria_<subsystem>_<measurement>_<unit>``, for example
``ria_ingestion_commit_resolve_seconds``. Names are declared as constants next to
the code that emits them, never assembled from user input, so that cardinality
cannot be influenced by a repository name appearing in a metric *name* rather
than a label.
"""

from __future__ import annotations

from types import TracebackType
from typing import Mapping, Optional, Protocol, Type, runtime_checkable

__all__ = ["MetricsSink", "Timer"]

#: Label values are always strings so that every backend can accept them without
#: coercion, and so that label cardinality is visible at the call site.
Labels = Mapping[str, str]


@runtime_checkable
class Timer(Protocol):
    """A context manager that records the duration of the block it wraps."""

    def __enter__(self) -> "Timer":
        """Start timing."""
        ...

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Stop timing and record the observation.

        Implementations must record the duration whether or not the block raised,
        and must label the observation with the outcome so that failure latency is
        distinguishable from success latency.
        """
        ...


@runtime_checkable
class MetricsSink(Protocol):
    """Destination for counters, gauges and duration observations.

    Implementations must be safe to call from multiple threads, must never raise,
    and must never block. A metrics backend failing is not a reason for an index
    build to fail; observability degrades, work continues.
    """

    def increment(
        self, name: str, value: int = 1, labels: Optional[Labels] = None
    ) -> None:
        """Add to a monotonically increasing counter.

        Args:
            name: Metric name following the module's naming convention.
            value: Non-negative amount to add.
            labels: Bounded-cardinality label set.
        """
        ...

    def gauge(self, name: str, value: float, labels: Optional[Labels] = None) -> None:
        """Record the current value of a point-in-time measurement.

        Args:
            name: Metric name.
            value: Current value.
            labels: Bounded-cardinality label set.
        """
        ...

    def observe(self, name: str, value: float, labels: Optional[Labels] = None) -> None:
        """Record a single observation in a distribution.

        Args:
            name: Metric name, suffixed with its unit.
            value: Observed value.
            labels: Bounded-cardinality label set.
        """
        ...

    def timer(self, name: str, labels: Optional[Labels] = None) -> Timer:
        """Create a timer that observes its own duration in seconds.

        Args:
            name: Metric name, conventionally suffixed ``_seconds``.
            labels: Bounded-cardinality label set.

        Returns:
            A context manager recording the wrapped block's duration.
        """
        ...
