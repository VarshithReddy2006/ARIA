"""WorkflowId value object.

Identifies a single Autonomous Workflow definition or execution instance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["WorkflowId"]


@dataclass(frozen=True)
class WorkflowId:
    """Opaque, immutable identifier for a Workflow.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("WorkflowId value must be a non-empty string")

    @classmethod
    def for_workflow(cls, name: str, instance_key: str) -> WorkflowId:
        """Construct a deterministic WorkflowId for a name and instance key.

        Args:
            name: Workflow classification name.
            instance_key: Instance identifier key.

        Returns:
            Deterministic WorkflowId.
        """
        raw_key = f"workflow:{name}:{instance_key}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"wf_{name[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
