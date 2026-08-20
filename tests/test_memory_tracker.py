"""Unit and regression tests for MemoryTracker utility and pipeline instrumentation."""

import logging
from unittest.mock import patch

from utils.memory_tracker import MemoryTracker, get_current_rss_mb


def test_get_current_rss_mb_returns_non_negative_float() -> None:
    """Verify that get_current_rss_mb returns a valid float value without raising."""
    rss = get_current_rss_mb()
    assert isinstance(rss, float)
    assert rss >= 0.0


def test_get_current_rss_mb_fallbacks() -> None:
    """Verify get_current_rss_mb handles psutil and /proc failures gracefully."""
    with (
        patch("builtins.__import__", side_effect=ImportError("No psutil")),
        patch("builtins.open", side_effect=OSError("No /proc")),
    ):
        rss = get_current_rss_mb()
        assert isinstance(rss, float)
        assert rss >= 0.0


def test_memory_tracker_log_phase_format(caplog) -> None:
    """Verify memory log line format contains all required fields."""
    tracker = MemoryTracker(
        repo_name="owner/repo", log_interval_files=2, log_interval_chunks=2
    )
    tracker.files_processed = 10
    tracker.bytes_processed = 1024
    tracker.chunks_processed = 50
    tracker.embeddings_indexed = 40

    with caplog.at_level(logging.INFO):
        tracker.log_phase("before_clone", custom_key="custom_val")

    assert "MEMORY phase=before_clone" in caplog.text
    assert "rss_mb=" in caplog.text
    assert "files_processed=10" in caplog.text
    assert "bytes_processed=1024" in caplog.text
    assert "chunks_processed=50" in caplog.text
    assert "embeddings_indexed=40" in caplog.text
    assert "elapsed_seconds=" in caplog.text
    assert "repo=owner/repo" in caplog.text
    assert "custom_key=custom_val" in caplog.text


def test_memory_tracker_periodic_file_extraction_logging(caplog) -> None:
    """Verify that during_extraction is logged every N files."""
    tracker = MemoryTracker(repo_name="owner/repo", log_interval_files=2)

    with caplog.at_level(logging.INFO):
        tracker.record_file(num_bytes=100)
        assert "during_extraction" not in caplog.text

        tracker.record_file(num_bytes=200)
        assert "MEMORY phase=during_extraction" in caplog.text
        assert "files_processed=2" in caplog.text
        assert "bytes_processed=300" in caplog.text


def test_memory_tracker_periodic_chunking_logging(caplog) -> None:
    """Verify that during_chunking is logged every N chunks."""
    tracker = MemoryTracker(repo_name="owner/repo", log_interval_chunks=5)

    with caplog.at_level(logging.INFO):
        tracker.record_chunk(3)
        assert "during_chunking" not in caplog.text

        tracker.record_chunk(3)
        assert "MEMORY phase=during_chunking" in caplog.text
        assert "chunks_processed=6" in caplog.text


def test_memory_tracker_record_embeddings() -> None:
    """Verify record_embeddings_indexed increments tracked total."""
    tracker = MemoryTracker(repo_name="owner/repo")
    tracker.record_embeddings_indexed(256)
    tracker.record_embeddings_indexed(128)
    assert tracker.embeddings_indexed == 384
