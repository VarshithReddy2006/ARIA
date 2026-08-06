"""Integration tests for SqliteReasoningCacheStore (Phase 10)."""

from __future__ import annotations

import pytest

from ria.domain.models.reasoning_result import (
    ReasoningCacheKey,
    ReasoningFingerprint,
    ReasoningResult,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.reasoning_store import SqliteReasoningCacheStore


@pytest.fixture
def reasoning_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_reasoning_cache_store(reasoning_db: ConnectionProvider) -> None:
    cache = SqliteReasoningCacheStore(reasoning_db)

    fp = ReasoningFingerprint(
        prompt_digest="digest1", provider_name="local", model_name="mock"
    )
    key = ReasoningCacheKey(fingerprint=fp)

    res = ReasoningResult(answer="Grounded answer text")

    cache.put(key, res)
    cached = cache.get(key)

    assert cached is not None
    assert cached.answer == "Grounded answer text"
    assert cached.statistics.cache_hit
