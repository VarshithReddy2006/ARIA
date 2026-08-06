"""TwinId value object.

Identifies a single Repository Digital Twin instance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ria.domain.identity import RepositoryId

__all__ = ["TwinId"]


@dataclass(frozen=True)
class TwinId:
    """Opaque, immutable identifier for a Repository Digital Twin.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("TwinId value must be a non-empty string")

    @classmethod
    def for_repository(cls, repository_id: RepositoryId | str) -> TwinId:
        """Construct a deterministic TwinId for a repository identity.

        Args:
            repository_id: Repository identity string or RepositoryId object.

        Returns:
            Deterministic TwinId.
        """
        raw_key = f"twin:{repository_id.value if hasattr(repository_id, 'value') else repository_id}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"twin_{digest}")

    def __str__(self) -> str:
        return self.value
