"""Job state machine and lifecycle models for asynchronous repository analysis."""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobStatus(str, enum.Enum):
    """Explicit job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobState(BaseModel):
    """Complete structured model for a repository analysis job."""

    job_id: str
    request_id: str
    repo_url: str
    branch: str = "main"
    repo: Dict[str, str] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    step_id: str = "clone"
    current_phase: str = "cloning"
    message: str = "Analysis queued"
    progress: int = 0
    items_processed: int = 0
    items_total: int = 0
    error: Optional[str] = None
    retry_count: int = 0
    stats: Dict[str, Any] = Field(default_factory=dict)
    successful_phases: list[str] = Field(default_factory=list)
    failed_phases: list[str] = Field(default_factory=list)
    skipped_phases: list[str] = Field(default_factory=list)
    phase_errors: Dict[str, str] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    updated_at: float = Field(default_factory=time.time)

    def transition_to(
        self,
        status: JobStatus,
        step_id: Optional[str] = None,
        message: Optional[str] = None,
        progress: Optional[int] = None,
        error: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> None:
        """Apply state transition with automatic timestamp tracking."""
        self.status = status
        now = time.time()
        self.updated_at = now

        if status == JobStatus.RUNNING and self.started_at is None:
            self.started_at = now
        elif status in (
            JobStatus.COMPLETED,
            JobStatus.PARTIAL,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ):
            self.completed_at = now

        if step_id is not None:
            self.step_id = step_id
        if message is not None:
            self.message = message
        if progress is not None:
            self.progress = max(0, min(100, progress))
        if error is not None:
            self.error = error
        if result is not None:
            self.result = result

        for k, v in extra.items():
            if hasattr(self, k):
                setattr(self, k, v)
