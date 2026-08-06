"""TaskId value object.

Identifies a single task in an agent execution plan.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

__all__ = ["TaskId"]


@dataclass(frozen=True)
class TaskId:
    """Opaque, immutable identifier for an Agent Task.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("TaskId value must be a non-empty string")

    @classmethod
    def for_task(cls, task_type: str, title: str) -> TaskId:
        """Construct a deterministic TaskId for a task type and title.

        Args:
            task_type: Type/kind of task.
            title: Task title or description.

        Returns:
            Deterministic TaskId.
        """
        raw_key = f"task:{task_type}:{title}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"tsk_{task_type[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
