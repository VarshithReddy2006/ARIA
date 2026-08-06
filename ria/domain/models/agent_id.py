"""AgentId value object.

Identifies a single specialized AI Agent definition or instance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["AgentId"]


@dataclass(frozen=True)
class AgentId:
    """Opaque, immutable identifier for an AI Agent.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("AgentId value must be a non-empty string")

    @classmethod
    def for_agent(cls, role_name: str, instance_key: str) -> AgentId:
        """Construct a deterministic AgentId for a role name and instance key.

        Args:
            role_name: Agent role (e.g. 'analyst', 'reviewer', 'security').
            instance_key: Instance identifier key.

        Returns:
            Deterministic AgentId.
        """
        raw_key = f"agent:{role_name}:{instance_key}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"agt_{role_name[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
