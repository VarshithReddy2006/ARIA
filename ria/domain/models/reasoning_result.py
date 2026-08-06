"""Reasoning result value objects.

Defines ReasoningEvidence, ReasoningCitation, ResponseQuality, ValidationResult,
ReasoningMetadata, ReasoningStatistics, ReasoningResult, ReasoningFingerprint,
and ReasoningCacheKey.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Optional, Tuple

__all__ = [
    "ReasoningEvidence",
    "ReasoningCitation",
    "ResponseQuality",
    "ValidationResult",
    "ReasoningMetadata",
    "ReasoningStatistics",
    "ReasoningResult",
    "ReasoningFingerprint",
    "ReasoningCacheKey",
]


@dataclass(frozen=True)
class ReasoningEvidence:
    """Evidence backing a grounded reasoning claim.

    Attributes:
        evidence_id: Unique evidence identifier.
        source_file: File path location.
        content_snippet: Supporting content text.
    """

    evidence_id: str
    source_file: str
    content_snippet: str


@dataclass(frozen=True)
class ReasoningCitation:
    """Structured citation attached to a grounded response.

    Attributes:
        file_path: Relative file path.
        line_range: Optional line range tuple (start, end).
        symbol_name: Optional symbol moniker.
        repository: Repository identity string.
    """

    file_path: str
    line_range: Optional[Tuple[int, int]] = None
    symbol_name: Optional[str] = None
    repository: str = "repository"


@dataclass(frozen=True)
class ResponseQuality:
    """Quality metrics evaluated for a reasoning response.

    Attributes:
        groundedness_score: Score in [0.0, 1.0] measuring evidence backing.
        citation_accuracy: Score in [0.0, 1.0] measuring citation correctness.
    """

    groundedness_score: float = 1.0
    citation_accuracy: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.groundedness_score <= 1.0:
            raise ValueError(
                f"groundedness_score must be within [0, 1], got {self.groundedness_score}"
            )
        if not 0.0 <= self.citation_accuracy <= 1.0:
            raise ValueError(
                f"citation_accuracy must be within [0, 1], got {self.citation_accuracy}"
            )


@dataclass(frozen=True)
class ValidationResult:
    """Validation report verifying grounded reasoning claims against evidence.

    Attributes:
        is_valid: True if response is grounded and fully supported.
        unsupported_claims: Claims lacking repository evidence.
        validated_claims: Verified evidence-backed claims.
    """

    is_valid: bool = True
    unsupported_claims: Tuple[str, ...] = ()
    validated_claims: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReasoningMetadata:
    """Provenance metadata for an AI Reasoning execution.

    Attributes:
        reasoning_id: Identity of the execution.
        provider_name: Model provider name.
        model_name: Executed model name.
        created_at_iso: UTC execution timestamp.
    """

    reasoning_id: str
    provider_name: str
    model_name: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class ReasoningStatistics:
    """Execution statistics for a reasoning request.

    Attributes:
        latency_seconds: Total execution latency in seconds.
        prompt_tokens: Input prompt token count.
        completion_tokens: Generated completion token count.
        cache_hit: True if served from reasoning cache.
    """

    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit: bool = False

    def __post_init__(self) -> None:
        if self.latency_seconds < 0.0:
            raise ValueError(
                f"latency_seconds must be non-negative, got {self.latency_seconds}"
            )
        if self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise ValueError("Token counts must be non-negative")


@dataclass(frozen=True)
class ReasoningResult:
    """Complete grounded AI Reasoning result container.

    Attributes:
        answer: Final evidence-backed response answer string.
        evidence: Supporting ReasoningEvidence items.
        citations: Structured ReasoningCitation items.
        validation: Groundedness ValidationResult.
        quality: ResponseQuality metrics.
        statistics: ReasoningStatistics execution stats.
        metadata: ReasoningMetadata provenance.
    """

    answer: str
    evidence: Tuple[ReasoningEvidence, ...] = ()
    citations: Tuple[ReasoningCitation, ...] = ()
    validation: ValidationResult = field(default_factory=ValidationResult)
    quality: ResponseQuality = field(default_factory=ResponseQuality)
    statistics: ReasoningStatistics = field(default_factory=ReasoningStatistics)
    metadata: ReasoningMetadata = field(
        default_factory=lambda: ReasoningMetadata("rsn", "local", "mock")
    )


@dataclass(frozen=True)
class ReasoningFingerprint:
    """Fingerprint representing prompt text, provider, and model.

    Attributes:
        prompt_digest: SHA-256 digest of input prompt text.
        provider_name: Provider identifier.
        model_name: Model identifier.
    """

    prompt_digest: str
    provider_name: str
    model_name: str

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.provider_name}:{self.model_name}:{self.prompt_digest}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReasoningCacheKey:
    """Content-addressed lookup key for reasoning result caching.

    Attributes:
        fingerprint: ReasoningFingerprint.
    """

    fingerprint: ReasoningFingerprint

    def digest(self) -> str:
        """Compute SHA-256 hex digest of cache key."""
        raw = f"reasoning_cache:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
