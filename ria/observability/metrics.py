"""Metrics sink implementations.

Two adapters for :class:`~ria.ports.metrics.MetricsSink`, both complete:

:class:`InMemoryMetricsSink`
    Accumulates measurements in process. Serves as the default sink and as the
    assertion surface for tests, which is why it exposes read accessors rather
    than only accepting writes. A test asserting that an operation was counted is
    a test asserting the operation happened.

:class:`NullMetricsSink`
    Discards everything. Selected when metrics are disabled, so that disabling
    observability removes a sink rather than adding conditionals at every call
    site.

A Prometheus adapter is deliberately absent. Exposition is a delivery-layer
concern and belongs with the HTTP surface; adding it here would make this package
depend on a web framework's registry, which SDD section 2.3 forbids.

Both implementations satisfy the port's contract that a sink must never raise and
never block.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import Dict, List, Mapping, Optional, Tuple, Type

from ria.ports.metrics import Labels

__all__ = ["MetricKey", "Distribution", "InMemoryMetricsSink", "NullMetricsSink"]


@dataclass(frozen=True)
class MetricKey:
    """Identity of one metric series: its name plus its label values.

    Labels are stored as a sorted tuple so that two calls supplying the same
    labels in different order address the same series.

    Attributes:
        name: Metric name.
        labels: Label pairs, sorted by key.
    """

    name: str
    labels: Tuple[Tuple[str, str], ...] = ()

    @classmethod
    def of(cls, name: str, labels: Optional[Labels]) -> "MetricKey":
        """Build a key from a name and an optional label mapping.

        Args:
            name: Metric name.
            labels: Label mapping, or ``None``.
        """
        if not labels:
            return cls(name=name)
        return cls(
            name=name, labels=tuple(sorted((str(k), str(v)) for k, v in labels.items()))
        )

    def __str__(self) -> str:
        if not self.labels:
            return self.name
        rendered = ",".join(f"{key}={value}" for key, value in self.labels)
        return f"{self.name}{{{rendered}}}"


@dataclass
class Distribution:
    """Summary statistics for a series of observations.

    Full observation values are retained up to :attr:`RETENTION_LIMIT` so that a
    test can assert on percentiles. Beyond that only the aggregates continue to
    update, which bounds memory for a long-running process while keeping the
    count and total exact.

    Attributes:
        count: Number of observations.
        total: Sum of observed values.
        minimum: Smallest observation, or ``None`` before the first.
        maximum: Largest observation, or ``None`` before the first.
        samples: Retained observation values.
    """

    #: Maximum number of individual observations retained per series.
    RETENTION_LIMIT = 1_000

    count: int = 0
    total: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    samples: List[float] = field(default_factory=list)

    def record(self, value: float) -> None:
        """Fold an observation into the distribution.

        Args:
            value: Observed value.
        """
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        if len(self.samples) < self.RETENTION_LIMIT:
            self.samples.append(value)

    @property
    def mean(self) -> Optional[float]:
        """Arithmetic mean, or ``None`` before the first observation."""
        return self.total / self.count if self.count else None


class _InMemoryTimer:
    """Timer that records its own duration and outcome on exit.

    Labels the observation with ``outcome=success`` or ``outcome=error`` so that
    failure latency is distinguishable from success latency, as the
    :class:`~ria.ports.metrics.Timer` contract requires.
    """

    __slots__ = ("_sink", "_name", "_labels", "_started")

    def __init__(
        self, sink: "InMemoryMetricsSink", name: str, labels: Optional[Labels]
    ) -> None:
        self._sink = sink
        self._name = name
        self._labels = dict(labels or {})
        self._started = 0.0

    def __enter__(self) -> "_InMemoryTimer":
        self._started = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        elapsed = time.perf_counter() - self._started
        labels = dict(self._labels)
        labels["outcome"] = "success" if exc_type is None else "error"
        self._sink.observe(self._name, elapsed, labels)


class InMemoryMetricsSink:
    """Metrics sink that accumulates measurements in process.

    Thread-safe. Every mutation holds a lock, which is acceptable because metric
    emission is orders of magnitude cheaper than the work being measured.

    Satisfies :class:`~ria.ports.metrics.MetricsSink`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[MetricKey, int] = {}
        self._gauges: Dict[MetricKey, float] = {}
        self._distributions: Dict[MetricKey, Distribution] = {}

    # -- MetricsSink ------------------------------------------------------

    def increment(
        self, name: str, value: int = 1, labels: Optional[Labels] = None
    ) -> None:
        """Add to a counter. Negative values are ignored rather than raising.

        Args:
            name: Metric name.
            value: Non-negative amount to add.
            labels: Label mapping.
        """
        if value < 0:
            return
        key = MetricKey.of(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, labels: Optional[Labels] = None) -> None:
        """Set the current value of a gauge.

        Args:
            name: Metric name.
            value: Current value.
            labels: Label mapping.
        """
        key = MetricKey.of(name, labels)
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float, labels: Optional[Labels] = None) -> None:
        """Record an observation in a distribution.

        Args:
            name: Metric name.
            value: Observed value.
            labels: Label mapping.
        """
        key = MetricKey.of(name, labels)
        with self._lock:
            distribution = self._distributions.get(key)
            if distribution is None:
                distribution = Distribution()
                self._distributions[key] = distribution
            distribution.record(float(value))

    def timer(self, name: str, labels: Optional[Labels] = None) -> _InMemoryTimer:
        """Create a timer that observes its duration in seconds on exit.

        Args:
            name: Metric name, conventionally suffixed ``_seconds``.
            labels: Label mapping.

        Returns:
            A context manager.
        """
        return _InMemoryTimer(self, name, labels)

    # -- inspection -------------------------------------------------------

    def counter_value(self, name: str, labels: Optional[Labels] = None) -> int:
        """Read a counter, returning zero when the series does not exist.

        Args:
            name: Metric name.
            labels: Label mapping.
        """
        with self._lock:
            return self._counters.get(MetricKey.of(name, labels), 0)

    def gauge_value(
        self, name: str, labels: Optional[Labels] = None
    ) -> Optional[float]:
        """Read a gauge, returning ``None`` when the series does not exist.

        Args:
            name: Metric name.
            labels: Label mapping.
        """
        with self._lock:
            return self._gauges.get(MetricKey.of(name, labels))

    def distribution(
        self, name: str, labels: Optional[Labels] = None
    ) -> Optional[Distribution]:
        """Read a distribution, returning ``None`` when the series does not exist.

        Args:
            name: Metric name.
            labels: Label mapping.
        """
        with self._lock:
            return self._distributions.get(MetricKey.of(name, labels))

    def counters(self) -> Mapping[MetricKey, int]:
        """Snapshot of every counter series."""
        with self._lock:
            return dict(self._counters)

    def gauges(self) -> Mapping[MetricKey, float]:
        """Snapshot of every gauge series."""
        with self._lock:
            return dict(self._gauges)

    def distributions(self) -> Mapping[MetricKey, Distribution]:
        """Snapshot of every distribution series."""
        with self._lock:
            return dict(self._distributions)

    def reset(self) -> None:
        """Discard every recorded measurement."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._distributions.clear()


class _NullTimer:
    """Timer that measures nothing."""

    __slots__ = ()

    def __enter__(self) -> "_NullTimer":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        return None


class NullMetricsSink:
    """Metrics sink that discards every measurement.

    Selected when ``RIA_OBS_METRICS_ENABLED`` is false. Satisfies
    :class:`~ria.ports.metrics.MetricsSink`.
    """

    __slots__ = ()

    def increment(
        self, name: str, value: int = 1, labels: Optional[Labels] = None
    ) -> None:
        """Discard a counter increment."""
        return None

    def gauge(self, name: str, value: float, labels: Optional[Labels] = None) -> None:
        """Discard a gauge value."""
        return None

    def observe(self, name: str, value: float, labels: Optional[Labels] = None) -> None:
        """Discard an observation."""
        return None

    def timer(self, name: str, labels: Optional[Labels] = None) -> _NullTimer:
        """Return a timer that measures nothing.

        Args:
            name: Ignored.
            labels: Ignored.
        """
        return _NullTimer()
