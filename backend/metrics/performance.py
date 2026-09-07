import time
import threading
from collections import defaultdict
from typing import Dict, List, Any
import psutil


class StageTimer:
    """Collect timing statistics for a named stage.

    Records total wall time, CPU time and counts of calls. Allows
    computation of average, percentiles and provides a simple report.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, List[float]] = defaultdict(list)
        self._cpu_records: Dict[str, List[float]] = defaultdict(list)
        self._call_counts: Dict[str, int] = defaultdict(int)
        self._start_times: Dict[str, float] = {}

    def start(self, stage: str) -> float:
        """Mark the start of a stage.

        Stores the start timestamp internally and also returns it for convenience.
        """
        ts = time.perf_counter()
        # Store the start time for later use if stop is called without explicit timestamp
        with self._lock:
            self._start_times[stage] = ts
        return ts

    def stop(self, stage: str, start_ts: float = None) -> None:
        """Record the elapsed time for *stage*.

        If ``start_ts`` is not provided, the method will look up the start time
        stored by ``start``. This makes the API compatible with existing calls
        that only pass the stage name.
        """
        # Retrieve start timestamp if not supplied
        if start_ts is None:
            with self._lock:
                start_ts = self._start_times.pop(stage, None)
            if start_ts is None:
                # Fallback: use current time to avoid errors (will record near zero)
                start_ts = time.perf_counter()
        elapsed = time.perf_counter() - start_ts
        cpu_elapsed = time.process_time() - start_ts  # approximate CPU time
        with self._lock:
            self._records[stage].append(elapsed)
            self._cpu_records[stage].append(cpu_elapsed)
            self._call_counts[stage] += 1

    def report(self) -> Dict[str, Any]:
        """Return a summary dict for all recorded stages."""
        report: Dict[str, Any] = {}
        for stage, times in self._records.items():
            if not times:
                continue
            times_sorted = sorted(times)
            total = sum(times)
            count = self._call_counts.get(stage, len(times))
            avg = total / count if count else 0.0
            p50 = times_sorted[int(0.5 * len(times_sorted))]
            p95 = times_sorted[int(0.95 * len(times_sorted))]
            cpu_total = sum(self._cpu_records.get(stage, []))
            report[stage] = {
                "call_count": count,
                "total_time": total,
                "average_time": avg,
                "p50": p50,
                "p95": p95,
                "cpu_time": cpu_total,
                "wall_time": total,
                "memory_mb": psutil.Process().memory_info().rss / (1024 * 1024),
            }
        return report

    def reset(self) -> None:
        """Clear all recorded data."""
        with self._lock:
            self._records.clear()
            self._cpu_records.clear()
            self._call_counts.clear()
