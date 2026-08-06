"""Metrics Port abstraction for telemetry measurements."""

from typing import Protocol, runtime_checkable

from ria.ports.common.logger import LogContextValue


@runtime_checkable
class MetricsPort(Protocol):
    """Protocol for collecting counters, gauges, histograms, and execution timers.

    Preconditions: Metric names must be non-empty strings. Tags must be primitive values.
    Postconditions: Telemetry metrics recorded.
    """

    def increment_counter(
        self, metric_name: str, value: int = 1, **tags: LogContextValue
    ) -> None:
        """Increment a monotonic counter metric."""
        ...

    def record_gauge(
        self, metric_name: str, value: float, **tags: LogContextValue
    ) -> None:
        """Set a gauge metric value."""
        ...

    def record_histogram(
        self, metric_name: str, value: float, **tags: LogContextValue
    ) -> None:
        """Record a observation in a histogram distribution metric."""
        ...

    def record_duration(
        self, metric_name: str, seconds: float, **tags: LogContextValue
    ) -> None:
        """Record an execution duration timing in seconds."""
        ...
