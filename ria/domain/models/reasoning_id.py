"""ReasoningId value object.

Identifies a single AI Reasoning execution request or cached reasoning result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["ReasoningId"]


@dataclass(frozen=True)
class ReasoningId:
    """Opaque, immutable identifier for a reasoning execution.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("ReasoningId value must be a non-empty string")

    @classmethod
    def for_reasoning(cls, model_name: str, query_digest: str) -> ReasoningId:
        """Construct a deterministic ReasoningId for a model and query digest.

        Args:
            model_name: Name of target model.
            query_digest: Hash or digest of prompt context.

        Returns:
            Deterministic ReasoningId.
        """
        raw_key = f"reasoning:{model_name}:{query_digest}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"rsn_{model_name[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
