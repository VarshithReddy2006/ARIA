"""Performance & Memory Metrics Collector for Benchmarks."""

import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, List


@dataclass(frozen=True, slots=True)
class StageMetric:
    """Metric recording for an individual pipeline stage execution."""

    stage_name: str
    start_time: float
    end_time: float
    elapsed_seconds: float
    peak_memory_bytes: int
    items_processed: int
    failures: int = 0
    warnings: int = 0

    @property
    def throughput_per_sec(self) -> float:
        if self.elapsed_seconds <= 0.0:
            return 0.0
        return self.items_processed / self.elapsed_seconds


@dataclass
class BenchmarkResult:
    """Comprehensive benchmark result container for a single repository run."""

    repo_name: str
    language: str
    file_count: int
    repo_size_bytes: int
    commit_sha: str
    branch: str
    total_elapsed_seconds: float
    peak_memory_bytes: int
    stage_metrics: List[StageMetric] = field(default_factory=list)

    @property
    def overall_throughput_files_per_sec(self) -> float:
        if self.total_elapsed_seconds <= 0.0:
            return 0.0
        return self.file_count / self.total_elapsed_seconds


class PerformanceCollector:
    """Context manager and tracker measuring execution latency, peak RAM, and throughput."""

    def __init__(self) -> None:
        self.stage_metrics: List[StageMetric] = []

    def measure_stage(
        self,
        stage_name: str,
        items_processed: int = 0,
        failures: int = 0,
        warnings: int = 0,
    ) -> "StageTracker":
        return StageTracker(self, stage_name, items_processed, failures, warnings)


class StageTracker:
    """Helper context manager tracking start/end time and tracemalloc peak memory."""

    def __init__(
        self,
        collector: PerformanceCollector,
        stage_name: str,
        items: int,
        failures: int,
        warnings: int,
    ) -> None:
        self._collector = collector
        self._stage_name = stage_name
        self._items = items
        self._failures = failures
        self._warnings = warnings
        self._start_time: float = 0.0

    def __enter__(self) -> "StageTracker":
        tracemalloc.start()
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        end_time = time.perf_counter()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        elapsed = end_time - self._start_time
        metric = StageMetric(
            stage_name=self._stage_name,
            start_time=self._start_time,
            end_time=end_time,
            elapsed_seconds=elapsed,
            peak_memory_bytes=peak,
            items_processed=self._items,
            failures=self._failures,
            warnings=self._warnings,
        )
        self._collector.stage_metrics.append(metric)
