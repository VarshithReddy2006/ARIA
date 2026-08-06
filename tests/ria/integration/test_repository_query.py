"""Integration tests for Milestone 7 — Repository Query & Analysis Engine (Phase 15)."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ria.application.query_service import RepositoryQueryService
from ria.application.twin_builder import TwinBuilderService
from ria.domain.identity import CommitSha, Moniker, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics
from ria.domain.models.graph_snapshot import GraphSnapshot
from ria.domain.models.query_id import QueryId
from ria.domain.models.query_request import QueryContext, QueryRequest
from ria.domain.models.repository import Repository
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.query_store import SqliteQueryCacheStore


@pytest.fixture
def query_engine_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_repository_query_integration(query_engine_db: ConnectionProvider) -> None:
    cache = SqliteQueryCacheStore(query_engine_db)
    svc = RepositoryQueryService(cache_store=cache)

    repo_id = RepositoryId("query-repo")
    sha = CommitSha("a" * 40)
    now = datetime.now(timezone.utc)

    repo = Repository(
        repository_id=repo_id,
        moniker=Moniker.parse("repo:github.com:org/query-repo"),
        origin_url="https://github.com/org/query-repo.git",
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
        GraphMetadata("query-repo", sha.value),
        GraphStatistics(),
    )

    builder = TwinBuilderService()
    twin = builder.build_twin(repo, sha, g_snap)

    # 1. Execute Query
    ctx = QueryContext(repository_id=repo_id, commit_sha=sha)
    qid = QueryId.for_query("symbol", "main")
    req = QueryRequest(
        query_id=qid, context=ctx, query_type="find_symbol", target_name="main"
    )

    res1 = svc.execute_query(twin, req)
    assert isinstance(res1.matches, tuple)

    # Cached Query Reuse
    res2 = svc.execute_query(twin, req)
    assert res2.statistics.cache_hit

    # 2. Dependency Analysis
    dep = svc.analyze_dependencies(twin)
    assert isinstance(dep.module_dependencies, dict)

    # 3. Impact Analysis
    impact = svc.analyze_impact(twin, ("src/main.py",))
    assert "src/main.py" in impact.target_files

    # 4. Architecture Analysis
    arch = svc.analyze_architecture(twin)
    assert isinstance(arch.layer_violations, tuple)

    # 5. Pattern Matching
    patterns = svc.match_patterns(twin, "class", "Main")
    assert isinstance(patterns, tuple)

    # 6. Cross References
    xrefs = svc.get_cross_references(twin, "main")
    assert isinstance(xrefs, tuple)
