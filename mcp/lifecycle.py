"""Extensible Task Lifecycle Model & Progress Tracking.

Defines standard task lifecycle states and progress tracking infrastructure
for long-running operations. The state enum is extensible for future additions
like TIMED_OUT, RETRYING, PAUSED, WAITING.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class TaskState(str, Enum):
    """Extensible enum of task lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    RETRYING = "retrying"
    PAUSED = "paused"
    WAITING = "waiting"


@dataclass
class ProgressUpdate:
    """Standardized task progress event payload."""

    task_id: str
    state: TaskState
    progress_percentage: float = 0.0
    step_description: str = ""
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize progress payload to dictionary."""
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "progress_percentage": round(self.progress_percentage, 1),
            "step_description": self.step_description,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskTracker:
    """In-memory progress and lifecycle state tracker for background MCP tasks."""

    def __init__(self) -> None:
        self._tasks: Dict[str, ProgressUpdate] = {}
        self._start_times: Dict[str, float] = {}

    def start_task(
        self, task_id: str, description: str = "Initialized"
    ) -> ProgressUpdate:
        """Register and mark a task as RUNNING."""
        now = time.time()
        self._start_times[task_id] = now
        update = ProgressUpdate(
            task_id=task_id,
            state=TaskState.RUNNING,
            progress_percentage=0.0,
            step_description=description,
            elapsed_seconds=0.0,
        )
        self._tasks[task_id] = update
        return update

    def update_progress(
        self,
        task_id: str,
        percentage: float,
        description: str,
        state: TaskState = TaskState.PROGRESS,
    ) -> ProgressUpdate:
        """Update an active task's progress."""
        elapsed = time.time() - self._start_times.get(task_id, time.time())
        update = ProgressUpdate(
            task_id=task_id,
            state=state,
            progress_percentage=min(max(percentage, 0.0), 100.0),
            step_description=description,
            elapsed_seconds=elapsed,
        )
        self._tasks[task_id] = update
        return update

    def complete_task(
        self, task_id: str, description: str = "Completed successfully"
    ) -> ProgressUpdate:
        """Mark a task as COMPLETED."""
        elapsed = time.time() - self._start_times.get(task_id, time.time())
        update = ProgressUpdate(
            task_id=task_id,
            state=TaskState.COMPLETED,
            progress_percentage=100.0,
            step_description=description,
            elapsed_seconds=elapsed,
        )
        self._tasks[task_id] = update
        return update

    def fail_task(self, task_id: str, error_message: str) -> ProgressUpdate:
        """Mark a task as FAILED."""
        elapsed = time.time() - self._start_times.get(task_id, time.time())
        update = ProgressUpdate(
            task_id=task_id,
            state=TaskState.FAILED,
            progress_percentage=self._tasks.get(
                task_id, ProgressUpdate(task_id, TaskState.FAILED)
            ).progress_percentage,
            step_description="Failed",
            elapsed_seconds=elapsed,
            error=error_message,
        )
        self._tasks[task_id] = update
        return update

    def get_status(self, task_id: str) -> Optional[ProgressUpdate]:
        """Retrieve progress status for a task."""
        return self._tasks.get(task_id)


# Global singleton task tracker
global_task_tracker = TaskTracker()
