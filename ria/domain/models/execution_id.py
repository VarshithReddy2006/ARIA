"""ExecutionId value object.

Identifies a single Repository Execution instance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["ExecutionId"]


@dataclass(frozen=True)
class ExecutionId:
    """Opaque, immutable identifier for a Repository Execution.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("ExecutionId value must be a non-empty string")

    @classmethod
    def for_execution(cls, workflow_id_str: str, instance_key: str) -> ExecutionId:
        """Construct a deterministic ExecutionId for a workflow ID string and instance key.

        Args:
            workflow_id_str: Parent workflow ID string.
            instance_key: Instance identifier key.

        Returns:
            Deterministic ExecutionId.
        """
        raw_key = f"execution:{workflow_id_str}:{instance_key}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"exc_{workflow_id_str[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
