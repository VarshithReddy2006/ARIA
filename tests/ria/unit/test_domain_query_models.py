"""Unit tests for Milestone 7 Phase 1 Query Domain Models."""

from __future__ import annotations

import pytest

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.analysis_models import (
    AnalysisResult,
    ArchitectureAnalysis,
    CrossReference,
    DependencyAnalysis,
    ImpactAnalysis,
    PatternMatch,
)
from ria.domain.models.query_id import QueryId
from ria.domain.models.query_identity import QueryCacheKey, QueryFingerprint
from ria.domain.models.query_request import (
    QueryContext,
    QueryFilter,
    QueryProjection,
    QueryRequest,
)
from ria.domain.models.query_result import (
    QueryMatch,
    QueryMetadata,
    QueryStatistics,
    QueryResult,
)


def test_query_id_invariants() -> None:
    qid1 = QueryId.for_query("symbol", "main")
    qid2 = QueryId.for_query("symbol", "main")

    assert qid1 == qid2
    assert str(qid1) == qid1.value

    with pytest.raises(ValueError, match="non-empty string"):
        QueryId("")


def test_query_request_and_context() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    ctx = QueryContext(repository_id=repo_id, commit_sha=sha, max_results=100)
    flt = QueryFilter(kinds=("function",))
    proj = QueryProjection(include_metrics=True)

    qid = QueryId.for_query("symbol", "main")
    req = QueryRequest(
        query_id=qid,
        context=ctx,
        query_type="find_symbol",
        target_name="main",
        filter=flt,
        projection=proj,
    )

    assert req.query_type == "find_symbol"
    assert req.context.max_results == 100
    assert "function" in req.filter.kinds
    assert req.projection.include_metrics

    with pytest.raises(ValueError, match="positive"):
        QueryContext(repository_id=repo_id, commit_sha=sha, max_results=0)


def test_query_identity_value_objects() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    fp = QueryFingerprint(query_type="find_symbol", target_name="main")
    key = QueryCacheKey(repository_id=repo_id, commit_sha=sha, fingerprint=fp)

    assert key.digest() is not None
    assert fp.digest() is not None


def test_query_result_and_matches() -> None:
    meta = QueryMetadata(query_id="q1", query_type="find_symbol")
    match = QueryMatch(
        id="m1", kind="function", name="main", qualified_name="app.main", score=0.95
    )
    stats = QueryStatistics(total_matches=1, execution_time_seconds=0.01)
    res = QueryResult(matches=(match,), statistics=stats, metadata=meta)

    assert res.metadata.query_type == "find_symbol"
    assert len(res.matches) == 1
    assert res.matches[0].name == "main"
    assert res.statistics.total_matches == 1

    with pytest.raises(ValueError, match="score must be within"):
        QueryMatch(
            id="m1", kind="function", name="main", qualified_name="app.main", score=1.5
        )


def test_analysis_domain_models() -> None:
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)

    dep = DependencyAnalysis(dependency_depth_max=3)
    impact = ImpactAnalysis(dependency_ripple_count=5)
    arch = ArchitectureAnalysis(layer_violations=("v1",))
    pm = PatternMatch(
        pattern_type="class", matched_element="MyClass", location_path="app.py"
    )
    xref = CrossReference(
        source_symbol="a",
        target_symbol="b",
        relation_kind="calls",
        source_file="a.py",
        target_file="b.py",
    )

    res = AnalysisResult(
        analysis_type="full",
        repository_id=repo_id,
        commit_sha=sha,
        dependency_analysis=dep,
        impact_analysis=impact,
        architecture_analysis=arch,
        pattern_matches=(pm,),
        cross_references=(xref,),
    )

    assert res.dependency_analysis.dependency_depth_max == 3
    assert res.impact_analysis.dependency_ripple_count == 5
    assert len(res.architecture_analysis.layer_violations) == 1
    assert len(res.pattern_matches) == 1
    assert len(res.cross_references) == 1
