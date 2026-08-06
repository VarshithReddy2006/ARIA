"""SynchronizationResult domain value object.

Captures the output of a Digital Twin synchronization run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ria.domain.enums import TwinState
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.consistency_report import ConsistencyReport
from ria.domain.models.twin_result import TwinDiagnostic

__all__ = ["SynchronizationResult"]


@dataclass(frozen=True)
class SynchronizationResult:
    """Result of synchronizing the Digital Twin with lower pipeline layers.

    Attributes:
        repository_id: Repository identity.
        commit_sha: Commit SHA synchronized.
        state: Final TwinState lifecycle state.
        duration_seconds: Time taken to complete synchronization in seconds.
        diagnostics: Diagnostics produced during synchronization.
        consistency_report: Layer consistency audit report.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    state: TwinState = TwinState.SYNCHRONIZED
    duration_seconds: float = 0.0
    diagnostics: Tuple[TwinDiagnostic, ...] = ()
    consistency_report: ConsistencyReport = ConsistencyReport()

    def __post_init__(self) -> None:
        if self.duration_seconds < 0.0:
            raise ValueError(
                f"duration_seconds must be non-negative, got {self.duration_seconds}"
            )
