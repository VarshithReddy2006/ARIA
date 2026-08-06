"""Agent execution and shared context domain models.

Defines ExecutionContext, ExecutionPlan, ExecutionSession, and SharedContext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Tuple

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_task import AgentTask, TaskDependency
from ria.domain.models.context_evidence import ContextEvidence
from ria.domain.models.prompt_context import PromptContext

__all__ = [
    "ExecutionContext",
    "ExecutionPlan",
    "ExecutionSession",
    "SharedContext",
]


@dataclass(frozen=True)
class ExecutionContext:
    """Bounded repository execution context.

    Attributes:
        repository_id: Identity of target repository.
        commit_sha: Bound commit SHA.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha


@dataclass(frozen=True)
class ExecutionPlan:
    """Multi-agent task DAG execution plan.

    Attributes:
        plan_id: Unique plan identifier string.
        tasks: Tuple of AgentTask entries.
        dependencies: Tuple of TaskDependency links.
    """

    plan_id: str
    tasks: Tuple[AgentTask, ...] = ()
    dependencies: Tuple[TaskDependency, ...] = ()


@dataclass(frozen=True)
class ExecutionSession:
    """Active multi-agent execution session.

    Attributes:
        session_id: Session identifier key.
        context: Bound ExecutionContext.
        plan: Active ExecutionPlan.
        created_at_iso: UTC creation timestamp.
    """

    session_id: str
    context: ExecutionContext
    plan: ExecutionPlan
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class SharedContext:
    """Versioned shared prompt and evidence context accessible by all agents.

    Attributes:
        prompt_context: Shared PromptContext.
        shared_evidence: Additional shared ContextEvidence items.
        version: Version revision sequence number.
    """

    prompt_context: PromptContext
    shared_evidence: Tuple[ContextEvidence, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError(f"version must be positive, got {self.version}")
