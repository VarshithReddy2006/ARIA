"""Context result and metadata value objects.

Defines RetrievalResult, RankingResult, CompressionResult, ContextMetadata, ContextStatistics,
ContextFingerprint, and ContextCacheKey.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Tuple

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.context_evidence import ContextCandidate, ContextEvidence

__all__ = [
    "RetrievalResult",
    "RankingResult",
    "CompressionResult",
    "ContextMetadata",
    "ContextStatistics",
    "ContextFingerprint",
    "ContextCacheKey",
]


@dataclass(frozen=True)
class RetrievalResult:
    """Output of repository retriever stage.

    Attributes:
        candidates: Tuple of retrieved ContextCandidate items.
        retrieval_time_seconds: Latency in seconds.
    """

    candidates: Tuple[ContextCandidate, ...] = ()
    retrieval_time_seconds: float = 0.0


@dataclass(frozen=True)
class RankingResult:
    """Output of ranking engine stage.

    Attributes:
        ranked_candidates: Tuple of ranked ContextCandidate items.
        ranking_time_seconds: Latency in seconds.
    """

    ranked_candidates: Tuple[ContextCandidate, ...] = ()
    ranking_time_seconds: float = 0.0


@dataclass(frozen=True)
class CompressionResult:
    """Output of context compression engine stage.

    Attributes:
        compressed_items: Tuple of compressed ContextEvidence items.
        original_token_count: Token count before compression.
        compressed_token_count: Token count after compression.
        compression_ratio: Fraction of tokens retained in [0.0, 1.0].
    """

    compressed_items: Tuple[ContextEvidence, ...] = ()
    original_token_count: int = 0
    compressed_token_count: int = 0
    compression_ratio: float = 1.0


@dataclass(frozen=True)
class ContextMetadata:
    """Provenance metadata for an AI Context package.

    Attributes:
        context_id: Context identifier.
        repository_id: Repository identity.
        commit_sha: Commit SHA.
        created_at_iso: UTC creation timestamp.
    """

    context_id: str
    repository_id: str
    commit_sha: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class ContextStatistics:
    """Quantitative summary statistics of a Context package.

    Attributes:
        candidates_retrieved: Total candidate items retrieved.
        evidence_selected: Total evidence items included.
        total_tokens: Assembled prompt token count.
        cache_hit: True if served from context cache.
    """

    candidates_retrieved: int = 0
    evidence_selected: int = 0
    total_tokens: int = 0
    cache_hit: bool = False


@dataclass(frozen=True)
class ContextFingerprint:
    """Fingerprint representing query text, intent, and token budget options.

    Attributes:
        query_text: User request text.
        intent_type: Classified intent type.
        max_tokens: Token limit.
    """

    query_text: str
    intent_type: str
    max_tokens: int = 8192

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.intent_type}:{self.query_text}:{self.max_tokens}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContextCacheKey:
    """Content-addressed lookup key for context caching.

    Attributes:
        repository_id: Repository identity.
        commit_sha: Commit SHA.
        fingerprint: ContextFingerprint.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    fingerprint: ContextFingerprint

    def digest(self) -> str:
        """Compute SHA-256 hex digest of cache key."""
        raw = f"context_cache:{self.repository_id.value}:{self.commit_sha.value}:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
