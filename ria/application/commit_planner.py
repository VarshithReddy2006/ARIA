"""Commit Planner application service.

Generates structured CommitPlans and CommitMessages without pushing commits automatically.
Implements :class:`~ria.ports.execution.CommitPlannerPort`.
"""

from __future__ import annotations

import hashlib
from typing import Tuple

from ria.domain.models.commit_pr_models import CommitMessage, CommitPlan
from ria.domain.models.repository_edit_models import RepositoryEdit
from ria.ports.execution import CommitPlannerPort

__all__ = ["CommitPlannerService"]


class CommitPlannerService(CommitPlannerPort):
    """Service for preparing structured CommitPlans."""

    def prepare_commit(
        self,
        branch_name: str,
        edits: Tuple[RepositoryEdit, ...],
        title: str,
        body: str = "",
    ) -> CommitPlan:
        """Prepare a CommitPlan for approval-aware staging."""
        msg = CommitMessage(title=title, body=body)
        plan_digest = hashlib.sha256(
            f"{branch_name}:{title}".encode("utf-8")
        ).hexdigest()[:16]

        return CommitPlan(
            plan_id=f"cp_{plan_digest}",
            branch_name=branch_name,
            commit_message=msg,
            edits=edits,
        )
