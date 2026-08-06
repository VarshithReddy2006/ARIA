"""Pull Request Builder application service.

Generates PullRequestDraft packages including PR title, description, evidence summary,
and validation summary without auto-submitting.
Implements :class:`~ria.ports.execution.PullRequestBuilderPort`.
"""

from __future__ import annotations

import hashlib

from ria.domain.models.commit_pr_models import (
    CommitPlan,
    MergeStrategy,
    PullRequestDraft,
)
from ria.ports.execution import PullRequestBuilderPort

__all__ = ["PullRequestBuilderService"]


class PullRequestBuilderService(PullRequestBuilderPort):
    """Service constructing structured PullRequestDraft packages."""

    def build_pull_request(
        self,
        plan: CommitPlan,
        summary_text: str,
    ) -> PullRequestDraft:
        """Build PullRequestDraft from CommitPlan and summary."""
        draft_digest = hashlib.sha256(
            f"{plan.plan_id}:{summary_text[:30]}".encode("utf-8")
        ).hexdigest()[:16]

        desc = (
            f"## Summary\n{summary_text}\n\n"
            f"## Execution Plan\n- Plan ID: {plan.plan_id}\n"
            f"- Changed files: {len(plan.edits)}\n\n"
            f"## Commit Details\n{plan.commit_message.body}"
        )

        return PullRequestDraft(
            draft_id=f"pr_{draft_digest}",
            title=plan.commit_message.title,
            description=desc,
            branch_name=plan.branch_name,
            target_branch="main",
            merge_strategy=MergeStrategy.SQUASH,
        )
