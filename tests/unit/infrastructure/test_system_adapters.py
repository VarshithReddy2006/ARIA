"""Unit tests for System Infrastructure Adapters."""

import time

from ria.infrastructure.system import (
    HashlibHashingAdapter,
    InMemoryMetricsAdapter,
    StandardLoggerAdapter,
    SystemClockAdapter,
)
from ria.ports.index.filesystem import FilesystemPort


class DummyFS(FilesystemPort):
    def read_bytes(self, path) -> bytes:
        return b"hello world"

    def walk_directory(self, root, ignore_patterns=()):
        return ()

    def exists(self, path) -> bool:
        return True

    def get_size(self, path) -> int:
        return 11


def test_system_clock_adapter() -> None:
    clock = SystemClockAdapter()
    ts = clock.now_utc()
    assert ts.iso_format is not None

    t1 = clock.monotonic_seconds()
    time.sleep(0.05)
    t2 = clock.monotonic_seconds()
    assert t2 >= t1


def test_hashlib_hashing_adapter() -> None:
    hasher = HashlibHashingAdapter()
    h1 = hasher.hash_bytes(b"hello world")
    assert len(h1.sha256_hex) == 64

    fs = DummyFS()
    h2 = hasher.hash_file(None, fs)
    assert h1 == h2


def test_in_memory_metrics_adapter() -> None:
    metrics = InMemoryMetricsAdapter()
    metrics.increment_counter("scan_total", 5)
    metrics.record_gauge("queue_depth", 12.5)
    metrics.record_duration("parse_latency", 0.045)

    assert metrics.counters["scan_total"] == 5
    assert metrics.gauges["queue_depth"] == 12.5
    assert metrics.durations["parse_latency"] == [0.045]


def test_standard_logger_adapter() -> None:
    logger = StandardLoggerAdapter("test_logger")
    logger.debug("Debug msg", repo_id="123")
    logger.info("Info msg", status="ok")
    logger.warning("Warn msg")
    logger.error("Error msg", exc=ValueError("test error"))
