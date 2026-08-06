"""Integration tests for SqliteContextCacheStore (Phase 11)."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.context_result import ContextCacheKey, ContextFingerprint
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptSection,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.context_store import SqliteContextCacheStore
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner


@pytest.fixture
def context_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_context_cache_store(context_db: ConnectionProvider) -> None:
    cache = SqliteContextCacheStore(context_db)
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)

    fp = ContextFingerprint(query_text="explain code", intent_type="explain_code")
    key = ContextCacheKey(repository_id=repo_id, commit_sha=sha, fingerprint=fp)

    sec = PromptSection(title="Section 1", content="hello world", token_count=2)
    cit = ContextCitation(repository="repo1", file_path="app.py")
    prompt = PromptContext(sections=(sec,), citations=(cit,), total_tokens=2)

    cache.put(key, prompt)
    cached = cache.get(key)

    assert cached is not None
    assert len(cached.sections) == 1
    assert cached.sections[0].title == "Section 1"
    assert cached.total_tokens == 2
