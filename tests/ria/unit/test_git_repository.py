"""Unit tests for GitRepositoryService (Phase 6)."""

from __future__ import annotations


from ria.domain.identity import CommitSha
from ria.infrastructure.git.git_repository import GitRepositoryService


def test_git_repository_service() -> None:
    head = CommitSha("a" * 40)
    svc = GitRepositoryService(current_branch="feature", head_sha=head)

    assert svc.get_status() == "clean"
    ver = svc.get_version()
    assert ver.branch == "feature"
    assert ver.commit_sha == head

    diff = svc.compute_diff(head, CommitSha("b" * 40))
    assert "diff --git" in diff
