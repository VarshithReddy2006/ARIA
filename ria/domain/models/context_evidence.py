"""Context evidence value objects.

Defines ContextCandidate, ContextEvidence, and ContextBundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ria.domain.identity import CommitSha, RepositoryId

__all__ = ["ContextCandidate", "ContextEvidence", "ContextBundle"]


@dataclass(frozen=True)
class ContextCandidate:
    """Candidate evidence item retrieved before ranking.

    Attributes:
        id: Entity or snippet identifier.
        kind: Entity classification kind.
        content: Text content or code snippet.
        location_path: File path location.
        raw_score: Initial unweighted score.
    """

    id: str
    kind: str
    content: str
    location_path: str
    raw_score: float = 1.0


@dataclass(frozen=True)
class ContextEvidence:
    """Ranked and selected context evidence item.

    Attributes:
        id: Entity or snippet identifier.
        kind: Entity classification kind.
        content: Text content or code snippet.
        location_path: File path location.
        score: Final weighted relevance score in [0.0, 1.0].
        line_range: Optional tuple of (start_line, end_line).
    """

    id: str
    kind: str
    content: str
    location_path: str
    score: float = 1.0
    line_range: Optional[Tuple[int, int]] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be within [0, 1], got {self.score}")


@dataclass(frozen=True)
class ContextBundle:
    """Grouped bundle of retrieved evidence for a repository snapshot.

    Attributes:
        repository_id: Repository identity.
        commit_sha: Commit SHA.
        evidence_items: Tuple of ContextEvidence items.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    evidence_items: Tuple[ContextEvidence, ...] = ()
