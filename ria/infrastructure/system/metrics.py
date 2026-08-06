"""In-Memory Metrics Adapter implementing MetricsPort."""

from collections import defaultdict
from typing import Dict, List

from ria.ports.common.logger import LogContextValue
from ria.ports.common.metrics import MetricsPort


class InMemoryMetricsAdapter(MetricsPort):
    """In-memory metrics collector for recording counter, gauge, and timer observations."""

    def __init__(self) -> None:
        self.counters: Dict[str, int] = defaultdict(int)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.durations: Dict[str, List[float]] = defaultdict(list)

    def increment_counter(
        self, metric_name: str, value: int = 1, **tags: LogContextValue
    ) -> None:
        self.counters[metric_name] += value

    def record_gauge(
        self, metric_name: str, value: float, **tags: LogContextValue
    ) -> None:
        self.gauges[metric_name] = value

    def record_histogram(
        self, metric_name: str, value: float, **tags: LogContextValue
    ) -> None:
        self.histograms[metric_name].append(value)

    def record_duration(
        self, metric_name: str, seconds: float, **tags: LogContextValue
    ) -> None:
        self.durations[metric_name].append(seconds)
