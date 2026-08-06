"""Workflow result and metadata value objects.

Defines WorkflowMetadata, WorkflowStatistics, WorkflowFingerprint, and WorkflowCacheKey.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib

__all__ = [
    "WorkflowMetadata",
    "WorkflowStatistics",
    "WorkflowFingerprint",
    "WorkflowCacheKey",
]


@dataclass(frozen=True)
class WorkflowMetadata:
    """Provenance metadata for autonomous workflow execution.

    Attributes:
        workflow_id_str: WorkflowId string.
        created_at_iso: UTC creation timestamp.
    """

    workflow_id_str: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class WorkflowStatistics:
    """Execution statistics for a workflow session.

    Attributes:
        steps_total: Total steps in workflow definition.
        steps_completed: Total steps executed successfully.
        duration_seconds: Latency in seconds.
        cache_hit: True if result retrieved from workflow cache.
    """

    steps_total: int = 0
    steps_completed: int = 0
    duration_seconds: float = 0.0
    cache_hit: bool = False

    def __post_init__(self) -> None:
        if self.steps_total < 0 or self.steps_completed < 0:
            raise ValueError("Step counters must be non-negative")
        if self.duration_seconds < 0.0:
            raise ValueError(
                f"duration_seconds must be non-negative, got {self.duration_seconds}"
            )


@dataclass(frozen=True)
class WorkflowFingerprint:
    """Fingerprint representing workflow definition and execution context.

    Attributes:
        workflow_name: Workflow definition name.
        commit_sha: Commit SHA string.
    """

    workflow_name: str
    commit_sha: str

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.workflow_name}:{self.commit_sha}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkflowCacheKey:
    """Content-addressed lookup key for workflow cache.

    Attributes:
        fingerprint: WorkflowFingerprint.
    """

    fingerprint: WorkflowFingerprint

    def digest(self) -> str:
        """Compute SHA-256 hex digest of cache key."""
        raw = f"wf_cache:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
