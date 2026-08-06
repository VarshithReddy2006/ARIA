"""Regression Test Suite for Foundation Iteration 1."""

from dataclasses import dataclass

from ria.evaluation.metrics.collector import BenchmarkResult


@dataclass(frozen=True, slots=True)
class PerformanceBaseline:
    """Performance baseline thresholds for zero-regression enforcement."""

    min_throughput_files_per_sec: float = 10.0
    max_memory_per_file_bytes: int = 100 * 1024  # 100KB per file max peak
    max_allowed_failures: int = 0


class RegressionSuite:
    """Evaluates benchmark results against baseline performance and stability thresholds."""

    def __init__(self, baseline: PerformanceBaseline = PerformanceBaseline()) -> None:
        self._baseline = baseline

    def verify_no_regression(self, result: BenchmarkResult) -> list[str]:
        """Verify that benchmark result meets or exceeds all performance baseline thresholds."""
        violations: list[str] = []

        if result.overall_throughput_files_per_sec < self._baseline.min_throughput_files_per_sec:
            violations.append(
                f"Throughput regression: {result.overall_throughput_files_per_sec:.2f} files/sec "
                f"is below threshold of {self._baseline.min_throughput_files_per_sec:.2f} files/sec."
            )

        if result.file_count > 0:
            memory_per_file = result.peak_memory_bytes / result.file_count
            if memory_per_file > self._baseline.max_memory_per_file_bytes:
                violations.append(
                    f"Memory footprint regression: {memory_per_file / 1024:.2f} KB/file "
                    f"exceeds ceiling of {self._baseline.max_memory_per_file_bytes / 1024:.2f} KB/file."
                )

        total_failures = sum(sm.failures for sm in result.stage_metrics)
        if total_failures > self._baseline.max_allowed_failures:
            violations.append(
                f"Pipeline failure regression: {total_failures} failures recorded "
                f"(max allowed: {self._baseline.max_allowed_failures})."
            )

        return violations
