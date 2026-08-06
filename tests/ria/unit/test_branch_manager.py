"""Unit tests for BranchManagerService (Phase 7)."""

from __future__ import annotations


from ria.application.branch_manager import BranchManagerService
from ria.domain.identity import CommitSha


def test_branch_manager_service() -> None:
    svc = BranchManagerService()
    sha = CommitSha("a" * 40)

    b = svc.create_branch("Feature Fix", sha)
    assert b.branch_name == "feature-fix"
    assert b.base_commit == sha

    assert svc.delete_branch("feature-fix")
    assert not svc.delete_branch("feature-fix")
