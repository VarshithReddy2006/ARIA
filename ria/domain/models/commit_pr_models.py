"""Commit and Pull Request domain models.

Defines CommitMessage, CommitPlan, MergeStrategy, and PullRequestDraft.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from ria.domain.models.repository_edit_models import RepositoryEdit

__all__ = [
    "CommitMessage",
    "CommitPlan",
    "MergeStrategy",
    "PullRequestDraft",
]


class MergeStrategy(str, Enum):
    """Git merge strategy enum for PullRequestDraft."""

    SQUASH = "squash"
    REBASE = "rebase"
    MERGE_COMMIT = "merge_commit"


@dataclass(frozen=True)
class CommitMessage:
    """Structured commit message title and description body.

    Attributes:
        title: Short single-line commit title.
        body: Detailed commit body explanation string.
    """

    title: str
    body: str = ""


@dataclass(frozen=True)
class CommitPlan:
    """Prepared commit plan container.

    Attributes:
        plan_id: Unique commit plan identifier.
        branch_name: Target branch name for commit.
        commit_message: Bound CommitMessage.
        edits: Tuple of RepositoryEdit items.
    """

    plan_id: str
    branch_name: str
    commit_message: CommitMessage
    edits: Tuple[RepositoryEdit, ...] = ()


@dataclass(frozen=True)
class PullRequestDraft:
    """Draft pull request package.

    Attributes:
        draft_id: Unique PR draft identifier.
        title: PR title.
        description: PR description body text.
        branch_name: Source branch name.
        target_branch: Target base branch name.
        merge_strategy: Preferred MergeStrategy.
    """

    draft_id: str
    title: str
    description: str
    branch_name: str
    target_branch: str = "main"
    merge_strategy: MergeStrategy = MergeStrategy.SQUASH
