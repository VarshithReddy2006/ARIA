"""Branch Manager application service.

Manages Git branch creation, naming policies, lifecycle, cleanup, and protection rules.
Implements :class:`~ria.ports.execution.BranchManagerPort`.
"""

from __future__ import annotations

from typing import Dict

from ria.domain.identity import CommitSha
from ria.domain.models.repository_edit_models import BranchDefinition
from ria.ports.execution import BranchManagerPort

__all__ = ["BranchManagerService"]


class BranchManagerService(BranchManagerPort):
    """Service managing Git branch definitions and lifecycle."""

    def __init__(self) -> None:
        self._branches: Dict[str, BranchDefinition] = {}

    def create_branch(
        self, branch_name: str, base_commit: CommitSha
    ) -> BranchDefinition:
        """Create and register a new BranchDefinition."""
        clean_name = branch_name.lower().replace(" ", "-")
        defn = BranchDefinition(branch_name=clean_name, base_commit=base_commit)
        self._branches[clean_name] = defn
        return defn

    def delete_branch(self, branch_name: str) -> bool:
        """Delete an existing branch."""
        clean_name = branch_name.lower().replace(" ", "-")
        if clean_name in self._branches:
            del self._branches[clean_name]
            return True
        return False
