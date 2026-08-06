"""Unit tests for PullRequestBuilderService (Phase 9)."""

from __future__ import annotations


from ria.application.pull_request_builder import PullRequestBuilderService
from ria.domain.models.commit_pr_models import CommitMessage, CommitPlan


def test_pull_request_builder_service() -> None:
    svc = PullRequestBuilderService()
    msg = CommitMessage(title="Refactor modules", body="Cleaned up imports")
    plan = CommitPlan(plan_id="p1", branch_name="feature", commit_message=msg)

    pr = svc.build_pull_request(plan, "Execution completed successfully.")

    assert pr.title == "Refactor modules"
    assert pr.branch_name == "feature"
    assert "Execution completed successfully" in pr.description
