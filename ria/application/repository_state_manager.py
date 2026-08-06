"""Repository State Manager application service.

Manages repository runtime state, current commit, branch, loaded components, and lifecycle transitions.
Implements :class:`~ria.ports.twin.TwinLifecyclePort`.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from ria.domain.enums import RepositoryStatus, TwinState
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.repository_state import RepositoryState
from ria.ports.twin import TwinLifecyclePort

__all__ = ["RepositoryStateManager"]


class RepositoryStateManager(TwinLifecyclePort):
    """Thread-safe manager for RepositoryState entities."""

    def __init__(self) -> None:
        self._states: Dict[RepositoryId, RepositoryState] = {}

    def get_state(self, repository_id: RepositoryId) -> Optional[RepositoryState]:
        """Look up active RepositoryState."""
        return self._states.get(repository_id)

    def initialize_state(
        self,
        repository_id: RepositoryId,
        initial_commit_sha: CommitSha,
        initial_branch: Optional[str] = None,
    ) -> RepositoryState:
        """Initialize RepositoryState for a repository."""
        state = RepositoryState(
            repository_id=repository_id,
            current_commit_sha=initial_commit_sha,
            current_branch=initial_branch,
            status=RepositoryStatus.ACTIVE,
            twin_state=TwinState.INITIALIZING,
            loaded_components=("repository",),
        )
        self._states[repository_id] = state
        return state

    def update_commit_and_branch(
        self,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
        branch: Optional[str] = None,
    ) -> RepositoryState:
        """Update current commit SHA and branch for a repository."""
        curr = self._states.get(repository_id)
        if curr is None:
            return self.initialize_state(repository_id, commit_sha, branch)

        updated = RepositoryState(
            repository_id=repository_id,
            current_commit_sha=commit_sha,
            current_branch=branch if branch is not None else curr.current_branch,
            status=curr.status,
            twin_state=curr.twin_state,
            loaded_components=curr.loaded_components,
        )
        self._states[repository_id] = updated
        return updated

    def transition_state(
        self,
        repository_id: RepositoryId,
        target_state: TwinState,
    ) -> RepositoryState:
        """Transition twin lifecycle state."""
        curr = self._states.get(repository_id)
        if curr is None:
            raise ValueError(
                f"repository state for {repository_id.value!r} not initialized"
            )

        updated = RepositoryState(
            repository_id=repository_id,
            current_commit_sha=curr.current_commit_sha,
            current_branch=curr.current_branch,
            status=curr.status,
            twin_state=target_state,
            loaded_components=curr.loaded_components,
        )
        self._states[repository_id] = updated
        return updated

    def register_loaded_components(
        self,
        repository_id: RepositoryId,
        components: Tuple[str, ...],
    ) -> RepositoryState:
        """Register active initialized components."""
        curr = self._states.get(repository_id)
        if curr is None:
            raise ValueError(
                f"repository state for {repository_id.value!r} not initialized"
            )

        combined = tuple(sorted(set(curr.loaded_components) | set(components)))
        updated = RepositoryState(
            repository_id=repository_id,
            current_commit_sha=curr.current_commit_sha,
            current_branch=curr.current_branch,
            status=curr.status,
            twin_state=curr.twin_state,
            loaded_components=combined,
        )
        self._states[repository_id] = updated
        return updated
