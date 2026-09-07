"""Retrieval Pipeline Sub-Stage Timer.

Lightweight instrumentation for measuring each sub-stage of the
retrieval pipeline (query preprocessing, embedding, vector search,
ranking, context assembly, prompt construction, etc.).

Usage::

    timer = RetrievalTimer()
    with timer.track("embedding"):
        embedding = service.generate_embedding(query)
    with timer.track("vector_search"):
        results = store.search(embedding)

    report = timer.report()
    # {'embedding': {'calls': 1, 'total_ms': 12.3, ...}, ...}
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List

logger = logging.getLogger(__name__)


class RetrievalTimer:
    """Collect sub-stage timing metrics for one retrieval request."""

    __slots__ = ("_stages", "_counts")

    def __init__(self) -> None:
        self._stages: Dict[str, List[float]] = {}
        self._counts: Dict[str, int] = {}

    @contextmanager
    def track(self, stage: str) -> Generator[None, None, None]:
        """Context manager that records wall-clock time for *stage*."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if stage not in self._stages:
                self._stages[stage] = []
                self._counts[stage] = 0
            self._stages[stage].append(elapsed_ms)
            self._counts[stage] += 1

    def record(self, stage: str, elapsed_ms: float) -> None:
        """Manually record a timing for *stage*."""
        if stage not in self._stages:
            self._stages[stage] = []
            self._counts[stage] = 0
        self._stages[stage].append(elapsed_ms)
        self._counts[stage] += 1

    def report(self) -> Dict[str, Dict[str, Any]]:
        """Return a summary dict for all recorded stages."""
        result: Dict[str, Dict[str, Any]] = {}
        for stage, times in self._stages.items():
            if not times:
                continue
            times_sorted = sorted(times)
            total = sum(times)
            count = self._counts.get(stage, len(times))
            avg = total / count if count else 0.0
            p50_idx = min(int(0.5 * len(times_sorted)), len(times_sorted) - 1)
            p95_idx = min(int(0.95 * len(times_sorted)), len(times_sorted) - 1)
            result[stage] = {
                "calls": count,
                "total_ms": round(total, 2),
                "avg_ms": round(avg, 2),
                "p50_ms": round(times_sorted[p50_idx], 2),
                "p95_ms": round(times_sorted[p95_idx], 2),
                "min_ms": round(times_sorted[0], 2),
                "max_ms": round(times_sorted[-1], 2),
            }
        return result

    def total_ms(self) -> float:
        """Return total time across all stages."""
        return sum(sum(t) for t in self._stages.values())

    def log_report(self, prefix: str = "RETRIEVAL_PROFILE") -> None:
        """Emit a structured log line with all sub-stage timings."""
        report = self.report()
        parts = []
        for stage, metrics in sorted(
            report.items(), key=lambda x: x[1]["total_ms"], reverse=True
        ):
            parts.append(f"{stage}={metrics['total_ms']:.1f}ms({metrics['calls']}x)")
        logger.info(
            "%s | total=%.1fms | %s",
            prefix,
            self.total_ms(),
            " ".join(parts),
        )
