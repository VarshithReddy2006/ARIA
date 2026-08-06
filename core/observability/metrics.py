"""Metrics Abstraction Component.

Application-level metrics interface decoupled from exposition formatters.
Allows exporting metrics to Prometheus, OpenTelemetry, Datadog, etc.

Memory safety
-------------
All runtime collections in :class:`MetricsCollector` are bounded:

* Duration series store cumulative ``count``/``total`` scalars (which is what a
  Prometheus summary exposes) plus a bounded ``deque`` of recent samples. This
  keeps ``*_sum``/``*_count`` values exactly as before while making per-series
  memory constant instead of growing once per observation.
* The number of distinct label sets (series) per metric family is capped, so an
  endpoint with unbounded path cardinality cannot grow the registry without
  limit. Existing series keep updating after the cap is reached; new label sets
  are dropped and a single warning is emitted per metric family.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Deque, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum recent samples retained per duration series.
DEFAULT_MAX_SAMPLES_PER_SERIES = 1000

# Maximum distinct label sets retained per metric family.
DEFAULT_MAX_SERIES = 5000


class DurationSeries:
    """Bounded observation series for a single duration metric label set.

    Keeps cumulative ``count`` and ``total`` (Prometheus summary semantics) so the
    exported values are independent of how many raw samples are retained, plus a
    bounded window of the most recent samples for percentile/debug use.
    """

    __slots__ = ("_count", "_total", "_samples")

    def __init__(self, max_samples: int = DEFAULT_MAX_SAMPLES_PER_SERIES) -> None:
        self._count: int = 0
        self._total: float = 0.0
        self._samples: Deque[float] = deque(maxlen=max_samples)

    def append(self, value: float) -> None:
        """Record one observation."""
        self._count += 1
        self._total += value
        self._samples.append(value)

    @property
    def count(self) -> int:
        """Cumulative number of observations."""
        return self._count

    @property
    def total(self) -> float:
        """Cumulative sum of all observations."""
        return self._total

    @property
    def samples(self) -> Tuple[float, ...]:
        """The bounded window of most recent observations."""
        return tuple(self._samples)

    def __len__(self) -> int:
        """Cumulative observation count (backward-compatible with list storage)."""
        return self._count

    def __iter__(self) -> Iterator[float]:
        """Iterate the retained recent samples."""
        return iter(self._samples)


class MetricsExporter(ABC):
    """Abstract interface for metrics exporters."""

    @abstractmethod
    def export(self, collector: "MetricsCollector", cache: Optional[Any] = None) -> str:
        """Render collected metrics into the target exporter format."""
        pass


class PrometheusExporter(MetricsExporter):
    """Renders metrics in Prometheus text-based exposition format."""

    def export(self, collector: "MetricsCollector", cache: Optional[Any] = None) -> str:
        lines: List[str] = []

        with collector.lock:
            # 1. HTTP Request Total
            lines.append("# HELP http_requests_total Total number of HTTP requests.")
            lines.append("# TYPE http_requests_total counter")
            for (method, path, status), count in collector.http_requests_total.items():
                lines.append(
                    f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}.0'
                )

            # 1b. HTTP Request Durations
            lines.append(
                "# HELP http_request_duration_seconds HTTP request latencies in seconds."
            )
            lines.append("# TYPE http_request_duration_seconds summary")
            for (
                method,
                path,
                status,
            ), series in collector.http_request_duration.items():
                total = series.total
                count = series.count
                lines.append(
                    f'http_request_duration_seconds_sum{{method="{method}",path="{path}",status="{status}"}} {total:.6f}'
                )
                lines.append(
                    f'http_request_duration_seconds_count{{method="{method}",path="{path}",status="{status}"}} {count}'
                )

            # 2. Active Requests
            lines.append(
                "# HELP active_requests_count Total number of active requests."
            )
            lines.append("# TYPE active_requests_count gauge")
            lines.append(f"active_requests_count {collector.active_requests}.0")

            # 3. Build Durations
            lines.append(
                "# HELP build_duration_seconds Build pipeline durations in seconds."
            )
            lines.append("# TYPE build_duration_seconds summary")
            for repo, series in collector.build_durations.items():
                total = series.total
                count = series.count
                lines.append(
                    f'build_duration_seconds_sum{{repository="{repo}"}} {total:.6f}'
                )
                lines.append(
                    f'build_duration_seconds_count{{repository="{repo}"}} {count}'
                )

            # 4. Analysis Task Durations
            lines.append(
                "# HELP analysis_task_duration_seconds Duration of individual analysis tasks in seconds."
            )
            lines.append("# TYPE analysis_task_duration_seconds summary")
            for (repo, task), series in collector.analysis_task_duration.items():
                total = series.total
                count = series.count
                lines.append(
                    f'analysis_task_duration_seconds_sum{{repository="{repo}",task="{task}"}} {total:.6f}'
                )
                lines.append(
                    f'analysis_task_duration_seconds_count{{repository="{repo}",task="{task}"}} {count}'
                )

            # 5. Cache Metrics
            lines.append("# HELP cache_hits_total Total number of analysis cache hits.")
            lines.append("# TYPE cache_hits_total counter")
            for key, count in collector.cache_hits.items():
                lines.append(f'cache_hits_total{{cache_key="{key}"}} {count}.0')

            lines.append(
                "# HELP cache_misses_total Total number of analysis cache misses."
            )
            lines.append("# TYPE cache_misses_total counter")
            for key, count in collector.cache_misses.items():
                lines.append(f'cache_misses_total{{cache_key="{key}"}} {count}.0')

        if cache is not None and hasattr(cache, "get_stats"):
            try:
                stats = cache.get_stats()
                lines.append(
                    "# HELP cache_size Total number of entries currently in the cache."
                )
                lines.append("# TYPE cache_size gauge")
                lines.append(f"cache_size {stats.get('size', 0)}.0")
            except Exception:
                pass

        return "\n".join(lines) + "\n"


class MetricsCollector:
    """Interface-agnostic metrics collector for recording system performance events.

    Args:
        default_exporter: Exporter used by :meth:`export` when none is supplied.
        max_series: Maximum distinct label sets retained per metric family.
        max_samples_per_series: Maximum recent samples retained per duration series.
    """

    def __init__(
        self,
        default_exporter: Optional[MetricsExporter] = None,
        *,
        max_series: int = DEFAULT_MAX_SERIES,
        max_samples_per_series: int = DEFAULT_MAX_SAMPLES_PER_SERIES,
    ) -> None:
        self.lock = threading.Lock()
        self.http_requests_total: Dict[Tuple[str, str, int], int] = {}
        self.http_request_duration: Dict[Tuple[str, str, int], DurationSeries] = {}
        self.active_requests: int = 0
        self.build_durations: Dict[str, DurationSeries] = {}
        self.analysis_task_duration: Dict[Tuple[str, str], DurationSeries] = {}
        self.cache_hits: Dict[str, int] = {}
        self.cache_misses: Dict[str, int] = {}
        self.default_exporter = default_exporter or PrometheusExporter()

        self._max_series = max_series
        self._max_samples_per_series = max_samples_per_series
        self._capped_families: set = set()

    # ------------------------------------------------------------------
    # Internal helpers — must be called while holding ``self.lock``
    # ------------------------------------------------------------------
    def _series_cap_reached(self, family: str, store: Dict[Any, Any], key: Any) -> bool:
        """Return True when ``key`` is a new label set that would exceed the cap."""
        if key in store or len(store) < self._max_series:
            return False
        if family not in self._capped_families:
            self._capped_families.add(family)
            logger.warning(
                "METRICS_SERIES_CAP_REACHED family=%s max_series=%d "
                "new label sets are being dropped to bound memory usage",
                family,
                self._max_series,
            )
        return True

    def _observe(
        self, family: str, store: Dict[Any, DurationSeries], key: Any, value: float
    ) -> None:
        """Record a duration observation into a bounded series."""
        if self._series_cap_reached(family, store, key):
            return
        series = store.get(key)
        if series is None:
            series = DurationSeries(max_samples=self._max_samples_per_series)
            store[key] = series
        series.append(value)

    # ------------------------------------------------------------------
    # Public recording API
    # ------------------------------------------------------------------
    def increment_request(self, method: str, path: str, status: int) -> None:
        with self.lock:
            key = (method, path, status)
            if self._series_cap_reached(
                "http_requests_total", self.http_requests_total, key
            ):
                return
            self.http_requests_total[key] = self.http_requests_total.get(key, 0) + 1

    def record_request_duration(
        self, method: str, path: str, status: int, duration_seconds: float
    ) -> None:
        with self.lock:
            self._observe(
                "http_request_duration_seconds",
                self.http_request_duration,
                (method, path, status),
                duration_seconds,
            )

    def increment_active_requests(self) -> None:
        with self.lock:
            self.active_requests += 1

    def decrement_active_requests(self) -> None:
        with self.lock:
            self.active_requests = max(0, self.active_requests - 1)

    def record_build_duration(self, repo_name: str, duration_seconds: float) -> None:
        with self.lock:
            self._observe(
                "build_duration_seconds",
                self.build_durations,
                repo_name,
                duration_seconds,
            )

    def record_task_duration(
        self, repo_name: str, task_name: str, duration_seconds: float
    ) -> None:
        with self.lock:
            self._observe(
                "analysis_task_duration_seconds",
                self.analysis_task_duration,
                (repo_name, task_name),
                duration_seconds,
            )

    def record_cache_access(self, hit: bool, cache_key: str = "default") -> None:
        with self.lock:
            store = self.cache_hits if hit else self.cache_misses
            family = "cache_hits_total" if hit else "cache_misses_total"
            if self._series_cap_reached(family, store, cache_key):
                return
            store[cache_key] = store.get(cache_key, 0) + 1

    def export(
        self, exporter: Optional[MetricsExporter] = None, cache: Optional[Any] = None
    ) -> str:
        """Export metrics using specified or default exporter."""
        exp = exporter or self.default_exporter
        return exp.export(self, cache=cache)

    def generate_prometheus_metrics(self, cache: Optional[Any] = None) -> str:
        """Backward-compatible shortcut method for Prometheus output."""
        return self.export(PrometheusExporter(), cache=cache)


# Global singleton instance
metrics_collector = MetricsCollector()
