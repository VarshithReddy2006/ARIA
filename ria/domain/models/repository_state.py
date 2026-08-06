"""RepositoryState domain entity.

Captures active runtime state, identity, commit, branch, and loaded components of a repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ria.domain.enums import RepositoryStatus, TwinState
from ria.domain.identity import CommitSha, RepositoryId

__all__ = ["RepositoryState"]


@dataclass(frozen=True)
class RepositoryState:
    """Active runtime state of a registered repository.

    Attributes:
        repository_id: Repository identity.
        current_commit_sha: Currently bound CommitSha.
        current_branch: Currently active branch name (if any).
        status: RepositoryStatus lifecycle state.
        twin_state: TwinState lifecycle state.
        loaded_components: Active initialized components (e.g. parser, semantic, graph).
    """

    repository_id: RepositoryId
    current_commit_sha: CommitSha
    current_branch: Optional[str] = None
    status: RepositoryStatus = RepositoryStatus.ACTIVE
    twin_state: TwinState = TwinState.SYNCHRONIZED
    loaded_components: Tuple[str, ...] = field(default_factory=tuple)
