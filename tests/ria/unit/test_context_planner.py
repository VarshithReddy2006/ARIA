"""Unit tests for ContextPlannerService (Phase 4)."""

from __future__ import annotations


from ria.application.context_planner import ContextPlannerService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.context_id import ContextId
from ria.domain.models.context_request import ContextRequest, IntentClassification


def test_context_planner_service() -> None:
    svc = ContextPlannerService()
    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    cid = ContextId.for_context("trace", "main")
    req = ContextRequest(
        context_id=cid,
        query_text="Trace dependencies in src/main.py for SymbolEngine",
        repository_id=repo_id,
        commit_sha=sha,
    )
    intent = IntentClassification(intent_type="trace_dependency")

    plan = svc.plan_context(req, intent)

    assert plan.graph_depth == 4
    assert "src/main.py" in plan.target_files
    assert "SymbolEngine" in plan.target_symbols
