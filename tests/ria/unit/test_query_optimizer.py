"""Unit tests for QueryOptimizer (Phase 10)."""

from __future__ import annotations


from ria.application.query_optimizer import QueryOptimizer
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.query_id import QueryId
from ria.domain.models.query_request import QueryContext, QueryRequest


def test_query_optimizer() -> None:
    opt = QueryOptimizer()

    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    ctx = QueryContext(repository_id=repo_id, commit_sha=sha)
    qid = QueryId.for_query("symbol", "main")
    req = QueryRequest(
        query_id=qid, context=ctx, query_type="find_symbol", target_name="main"
    )

    key = opt.build_cache_key(req)
    assert key.repository_id == repo_id
    assert key.commit_sha == sha
