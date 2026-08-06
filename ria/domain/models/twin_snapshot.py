"""TwinSnapshot domain entity.

Represents an immutable versioned snapshot of a Repository Digital Twin.
"""

from __future__ import annotations

from dataclasses import dataclass

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_identity import TwinFingerprint

__all__ = ["TwinSnapshot"]


@dataclass(frozen=True)
class TwinSnapshot:
    """Immutable versioned snapshot of a Repository Digital Twin.

    Attributes:
        twin_id: Identity of the digital twin.
        repository_id: Identity of the parent repository.
        commit_sha: Bound commit SHA snapshot point.
        twin: Bound RepositoryTwin entity.
        fingerprint: TwinFingerprint identity.
    """

    twin_id: TwinId
    repository_id: RepositoryId
    commit_sha: CommitSha
    twin: RepositoryTwin
    fingerprint: TwinFingerprint
