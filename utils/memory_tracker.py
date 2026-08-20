"""Lightweight RSS Memory Tracker for profiling repository analysis pipelines.

Provides cross-platform Resident Set Size (RSS) monitoring without heavy profiling
dependencies. Designed for high-frequency low-overhead telemetry in constrained
environments (such as 512 MB instances).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_current_rss_mb() -> float:
    """Return current process Resident Set Size (RSS) in MiB.

    Resolution strategy:
    1. psutil (cross-platform, fast C bindings)
    2. Linux /proc/self/statm (zero overhead on Linux/Render)
    3. Python standard library `resource` (Unix/macOS fallback)
    4. 0.0 fallback if unavailable
    """
    # 1. psutil
    try:
        import psutil

        return round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
    except Exception:
        pass

    # 2. Linux /proc/self/statm
    try:
        with open("/proc/self/statm", "r") as f:
            fields = f.read().split()
            if len(fields) >= 2:
                rss_pages = int(fields[1])
                page_size = os.sysconf("SC_PAGE_SIZE")
                return round((rss_pages * page_size) / (1024 * 1024), 2)
    except Exception:
        pass

    # 3. resource.getrusage (Unix / macOS)
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "darwin":
            return round(ru.ru_maxrss / (1024 * 1024), 2)
        # On Linux ru_maxrss is in KiB
        return round(ru.ru_maxrss / 1024, 2)
    except Exception:
        pass

    return 0.0


class MemoryTracker:
    """Tracks progression and logs process RSS at defined pipeline boundaries."""

    def __init__(
        self,
        repo_name: str = "",
        log_interval_files: int = 50,
        log_interval_chunks: int = 200,
        logger_instance: Optional[logging.Logger] = None,
    ) -> None:
        self.repo_name = repo_name
        self.log_interval_files = log_interval_files
        self.log_interval_chunks = log_interval_chunks
        self.log = logger_instance or logger

        self.start_time = time.time()
        self.files_processed: int = 0
        self.bytes_processed: int = 0
        self.chunks_processed: int = 0
        self.embeddings_indexed: int = 0

        self._last_logged_files: int = 0
        self._last_logged_chunks: int = 0

    def log_phase(self, phase: str, **kwargs: Any) -> float:
        """Log memory metrics for a given execution boundary.

        Format:
        MEMORY phase=<phase> rss_mb=<rss_mb> files_processed=<n> bytes_processed=<n>
               chunks_processed=<n> embeddings_indexed=<n> elapsed_seconds=<sec> [key=val ...]
        """
        rss_mb = get_current_rss_mb()
        elapsed_seconds = round(time.time() - self.start_time, 2)

        parts = [
            f"MEMORY phase={phase}",
            f"rss_mb={rss_mb:.1f}",
            f"files_processed={self.files_processed}",
            f"bytes_processed={self.bytes_processed}",
            f"chunks_processed={self.chunks_processed}",
            f"embeddings_indexed={self.embeddings_indexed}",
            f"elapsed_seconds={elapsed_seconds:.1f}",
        ]

        if self.repo_name:
            parts.append(f"repo={self.repo_name}")

        for k, v in kwargs.items():
            if isinstance(v, float):
                parts.append(f"{k}={v:.1f}")
            else:
                parts.append(f"{k}={v}")

        log_line = " ".join(parts)
        self.log.info(log_line)
        return rss_mb

    def record_file(self, num_bytes: int = 0) -> None:
        """Record an extracted file and log memory periodically."""
        self.files_processed += 1
        self.bytes_processed += num_bytes
        if self.files_processed - self._last_logged_files >= self.log_interval_files:
            self._last_logged_files = self.files_processed
            self.log_phase("during_extraction")

    def record_chunk(self, count: int = 1) -> None:
        """Record chunked tokens and log memory periodically."""
        self.chunks_processed += count
        if self.chunks_processed - self._last_logged_chunks >= self.log_interval_chunks:
            self._last_logged_chunks = self.chunks_processed
            self.log_phase("during_chunking")

    def record_embeddings_indexed(self, count: int) -> None:
        """Record indexed embeddings count."""
        self.embeddings_indexed += count
