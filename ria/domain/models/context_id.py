"""ContextId value object.

Identifies a single AI Context request, plan, or assembled prompt context package.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["ContextId"]


@dataclass(frozen=True)
class ContextId:
    """Opaque, immutable identifier for an AI Context retrieval package.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("ContextId value must be a non-empty string")

    @classmethod
    def for_context(cls, intent_type: str, target: str) -> ContextId:
        """Construct a deterministic ContextId for an intent and target query string.

        Args:
            intent_type: Classified intent type.
            target: Query target or expression.

        Returns:
            Deterministic ContextId.
        """
        raw_key = f"context:{intent_type}:{target}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"ctx_{intent_type[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
