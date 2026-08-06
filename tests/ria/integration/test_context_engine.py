"""Integration tests for Milestone 8 — AI Context & Retrieval Engine (Phase 15)."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ria.application.context_engine_service import ContextEngineService
from ria.application.twin_builder import TwinBuilderService
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.context_id import ContextId
from ria.domain.models.context_request import ContextRequest
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.repository import Repository
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.context_store import SqliteContextCacheStore
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner


@pytest.fixture
def context_engine_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_context_engine_end_to_end(context_engine_db: ConnectionProvider) -> None:
    cache = SqliteContextCacheStore(context_engine_db)
    svc = ContextEngineService(cache_store=cache)

    repo_id = RepositoryId("ai-repo")
    sha = CommitSha("a" * 40)
    now = datetime.now(timezone.utc)

    repo = Repository(
        repository_id=repo_id,
        moniker=Moniker.parse("repo:github.com:org/ai-repo"),
        origin_url="https://github.com/org/ai-repo.git",
        default_branch="main",
        tenant_id="default",
        registered_at=now,
        updated_at=now,
    )

    g_fp = GraphFingerprint("builder", "1.0.0")
    g_snap = GraphSnapshot(
        repo_id,
        sha,
        Graph(),
        g_fp,
        GraphMetadata("ai-repo", sha.value),
        GraphStatistics(),
    )

    builder = TwinBuilderService()
    twin = builder.build_twin(repo, sha, g_snap)

    cid = ContextId.for_context("explain", "main")
    req = ContextRequest(
        context_id=cid,
        query_text="Explain code architecture and find bug in src/main.py",
        repository_id=repo_id,
        commit_sha=sha,
    )

    # 1. Build Context Package
    prompt1 = svc.build_context(twin, req)
    assert len(prompt1.sections) > 0
    assert len(prompt1.messages) > 0
    assert prompt1.total_tokens >= 0

    # 2. Context Cache Hit
    prompt2 = svc.build_context(twin, req)
    assert prompt2.total_tokens == prompt1.total_tokens
