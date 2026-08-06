"""Timing Component.

Context manager and decorator for instrumenting performance metrics across
repository analysis, graph building, parsing, symbol search, and cache lookups
without modifying underlying business logic.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional

from core.observability.metrics import metrics_collector

logger = logging.getLogger(__name__)


@contextmanager
def time_operation(
    operation_name: str, repository: Optional[str] = None, slow_threshold: Optional[float] = None
) -> Generator[None, None, None]:
    """Instrument an operational block, recording duration to metrics and logging slow warnings."""
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        repo = repository or "global"
        metrics_collector.record_task_duration(repo, operation_name, elapsed)

        if slow_threshold and elapsed > slow_threshold:
            logger.warning(
                "SLOW_OPERATION operation=%s repository=%s duration_ms=%.2f threshold_seconds=%.2f",
                operation_name,
                repo,
                elapsed * 1000.0,
                slow_threshold,
            )
