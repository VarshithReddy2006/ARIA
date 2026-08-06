"""Agent result and metadata value objects.

Defines AgentMetadata, AgentStatistics, AgentFingerprint, AgentCacheKey, and ExecutionReport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from typing import Tuple

from ria.domain.models.agent_task import TaskResult
from ria.domain.models.prompt_context import ContextCitation

__all__ = [
    "AgentMetadata",
    "AgentStatistics",
    "AgentFingerprint",
    "AgentCacheKey",
    "ExecutionReport",
]


@dataclass(frozen=True)
class AgentMetadata:
    """Provenance metadata for multi-agent platform execution.

    Attributes:
        session_id: Session identifier.
        created_at_iso: UTC creation timestamp.
    """

    session_id: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class AgentStatistics:
    """Execution metrics for multi-agent execution session.

    Attributes:
        tasks_scheduled: Total tasks scheduled.
        tasks_succeeded: Total tasks completed successfully.
        tasks_failed: Total tasks failed.
        total_duration_seconds: Execution latency in seconds.
        cache_hit: True if served from execution cache.
    """

    tasks_scheduled: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    total_duration_seconds: float = 0.0
    cache_hit: bool = False

    def __post_init__(self) -> None:
        if (
            self.tasks_scheduled < 0
            or self.tasks_succeeded < 0
            or self.tasks_failed < 0
        ):
            raise ValueError("Task counters must be non-negative")
        if self.total_duration_seconds < 0.0:
            raise ValueError(
                f"total_duration_seconds must be non-negative, got {self.total_duration_seconds}"
            )


@dataclass(frozen=True)
class AgentFingerprint:
    """Fingerprint representing session plan and context.

    Attributes:
        plan_id: Execution plan identifier.
        query_text: User request text.
    """

    plan_id: str
    query_text: str

    def token(self) -> str:
        """Return canonical token string."""
        return f"{self.plan_id}:{self.query_text}"

    def digest(self) -> str:
        """Compute SHA-256 hex digest of fingerprint token."""
        return hashlib.sha256(self.token().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AgentCacheKey:
    """Content-addressed lookup key for execution report caching.

    Attributes:
        fingerprint: AgentFingerprint.
    """

    fingerprint: AgentFingerprint

    def digest(self) -> str:
        """Compute SHA-256 hex digest of cache key."""
        raw = f"agent_cache:{self.fingerprint.digest()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionReport:
    """Final aggregated multi-agent platform execution report.

    Attributes:
        session_id: Session identifier.
        summary_text: Unified synthesized answer text.
        task_results: Individual TaskResult items from participating agents.
        report_citations: Structured ContextCitation items.
        statistics: AgentStatistics metrics.
    """

    session_id: str
    summary_text: str
    task_results: Tuple[TaskResult, ...] = ()
    report_citations: Tuple[ContextCitation, ...] = ()
    statistics: AgentStatistics = field(default_factory=AgentStatistics)
