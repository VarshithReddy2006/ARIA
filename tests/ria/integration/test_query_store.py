"""Integration tests for SqliteQueryCacheStore (Phase 12)."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.query_identity import QueryCacheKey, QueryFingerprint
from ria.domain.models.query_result import QueryMatch, QueryResult
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.query_store import SqliteQueryCacheStore


@pytest.fixture
def query_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_query_cache_store(query_db: ConnectionProvider) -> None:
    cache = SqliteQueryCacheStore(query_db)
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)

    fp = QueryFingerprint(query_type="find_symbol", target_name="main")
    key = QueryCacheKey(repository_id=repo_id, commit_sha=sha, fingerprint=fp)

    match = QueryMatch(id="m1", kind="function", name="main", qualified_name="app.main")
    res = QueryResult(matches=(match,))

    cache.put(key, res)
    cached = cache.get(key)

    assert cached is not None
    assert len(cached.matches) == 1
    assert cached.matches[0].name == "main"
