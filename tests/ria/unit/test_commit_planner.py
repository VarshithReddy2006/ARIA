"""Unit tests for CommitPlannerService (Phase 8)."""

from __future__ import annotations


from ria.application.commit_planner import CommitPlannerService
from ria.domain.models.repository_edit_models import RepositoryEdit


def test_commit_planner_service() -> None:
    svc = CommitPlannerService()
    edit = RepositoryEdit(
        file_path="main.py", edit_type="modify", new_content="content"
    )

    plan = svc.prepare_commit(
        "feature", (edit,), "Feat: update main", "Detailed description"
    )

    assert plan.branch_name == "feature"
    assert plan.commit_message.title == "Feat: update main"
    assert len(plan.edits) == 1
