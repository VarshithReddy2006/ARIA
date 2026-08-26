"""Regression test suite for Phase 1: Persistence Correctness across container restarts."""

import os
import tempfile
import pytest
from core.config import settings
from backend.dependencies import (
    ANALYSIS_STORE,
    _persist_analysis_store,
)
from services.embedding_service import (
    _get_cached_embeddings_bulk,
    _save_embeddings_to_cache_bulk,
)
from storage.migrations import run_migrations


@pytest.mark.asyncio
async def test_analysis_store_persistence_across_restarts(monkeypatch):
    """Verify that analysis store persists state to disk and reloads cleanly upon simulated container restart."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "analysis_store.json")
        monkeypatch.setenv("ANALYSIS_STORE_PATH", store_path)

        # 1. First container instance writes analysis data
        test_payload = {
            "analysis": {
                "structure": {"src": ["main.py"]},
                "dependencies": [],
                "tech_stack": ["python"],
            },
            "architecture": {
                "summary": "Test Summary",
                "reading_order": [],
                "relationships": [],
            },
        }
        ANALYSIS_STORE["test-org/test-repo"] = test_payload
        await _persist_analysis_store()

        assert os.path.exists(store_path), "Backing file should exist after persist"

        # 2. Simulate container restart (clear in-memory dict and reload from disk)
        dict.clear(ANALYSIS_STORE)
        assert "test-org/test-repo" not in dict(ANALYSIS_STORE)

        # Triggers dynamic reload from disk
        assert "test-org/test-repo" in ANALYSIS_STORE
        restored = ANALYSIS_STORE["test-org/test-repo"]
        assert restored["architecture"].summary == "Test Summary"


def test_sqlite_l2_cache_persistence_across_restarts(monkeypatch):
    """Verify that SQLite L2 embedding cache persists across service re-instantiations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "repo_understanding.db")
        monkeypatch.setattr(settings, "sqlite_db_path", db_path)

        # Run migrations
        run_migrations()

        # 1. Save embeddings into L2 cache
        records = [
            {
                "chunk_hash": "hash_123456",
                "embedding": [0.1, 0.2, 0.3],
                "model_name": "BAAI/bge-small-en-v1.5",
                "model_version": "1.5",
            }
        ]
        _save_embeddings_to_cache_bulk(records)

        # 2. Re-open connection and query from L2 cache directly
        results = _get_cached_embeddings_bulk(["hash_123456"], "BAAI/bge-small-en-v1.5")
        assert "hash_123456" in results
        assert results["hash_123456"] == [0.1, 0.2, 0.3]
