"""Port protocols for Milestone 10 — Multi-Agent Developer Platform.

Defines runtime checkable protocols for task planning, agent registry, agent factory,
agent lifecycle management, orchestrator, shared context management, communication bus,
result aggregator, conflict resolution, and execution planning.
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol, Tuple, runtime_checkable

from ria.domain.models.agent_communication import AgentMessage
from ria.domain.models.agent_definition import AgentDefinition, AgentState
from ria.domain.models.agent_execution import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionSession,
    SharedContext,
)
from ria.domain.models.agent_id import AgentId
from ria.domain.models.agent_result import ExecutionReport
from ria.domain.models.agent_task import AgentTask, TaskResult
from ria.domain.models.prompt_context import PromptContext

__all__ = [
    "TaskPlannerPort",
    "AgentRegistryPort",
    "AgentFactoryPort",
    "AgentLifecyclePort",
    "AgentOrchestratorPort",
    "SharedContextPort",
    "CommunicationBusPort",
    "ResultAggregatorPort",
    "ConflictResolutionPort",
    "ExecutionPlannerPort",
]


@runtime_checkable
class TaskPlannerPort(Protocol):
    """Port for planning task decomposition from user request."""

    def plan_tasks(
        self,
        query_text: str,
        context: ExecutionContext,
    ) -> ExecutionPlan:
        """Construct ExecutionPlan task graph from query text."""
        ...


@runtime_checkable
class AgentRegistryPort(Protocol):
    """Port for discovering available specialized agent definitions."""

    def get_agent_definition(self, agent_id: AgentId) -> Optional[AgentDefinition]:
        """Look up AgentDefinition by AgentId."""
        ...

    def list_agent_definitions(self) -> Tuple[AgentDefinition, ...]:
        """List all registered AgentDefinitions."""
        ...


@runtime_checkable
class AgentFactoryPort(Protocol):
    """Port for instantiating specialized agent instances."""

    def create_agent(self, definition: AgentDefinition) -> AgentId:
        """Create and register an agent instance."""
        ...


@runtime_checkable
class AgentLifecyclePort(Protocol):
    """Port for managing agent lifecycle states."""

    def transition_state(self, agent_id: AgentId, new_state: AgentState) -> AgentState:
        """Transition agent to new state."""
        ...

    def terminate_agent(self, agent_id: AgentId) -> None:
        """Terminate active agent instance."""
        ...


@runtime_checkable
class AgentOrchestratorPort(Protocol):
    """Port for scheduling and orchestrating multi-agent task execution."""

    def execute_plan(
        self,
        session: ExecutionSession,
        shared_context: SharedContext,
    ) -> ExecutionReport:
        """Orchestrate ExecutionPlan across available agents."""
        ...


@runtime_checkable
class SharedContextPort(Protocol):
    """Port for accessing and updating versioned SharedContext."""

    def get_context(self) -> SharedContext:
        """Retrieve active SharedContext."""
        ...

    def update_context(self, prompt_context: PromptContext) -> SharedContext:
        """Update active SharedContext."""
        ...


@runtime_checkable
class CommunicationBusPort(Protocol):
    """Port for inter-agent communication bus."""

    def publish(self, message: AgentMessage) -> None:
        """Publish message to communication bus."""
        ...

    def subscribe(self, recipient_id: AgentId) -> Iterator[AgentMessage]:
        """Subscribe to messages targeting recipient_id or broadcast."""
        ...


@runtime_checkable
class ResultAggregatorPort(Protocol):
    """Port for aggregating individual agent task outputs into an ExecutionReport."""

    def aggregate_results(
        self,
        session_id: str,
        task_results: Tuple[TaskResult, ...],
    ) -> ExecutionReport:
        """Aggregate TaskResults into final ExecutionReport."""
        ...


@runtime_checkable
class ConflictResolutionPort(Protocol):
    """Port for resolving conflicting evidence or conclusions between agent outputs."""

    def resolve_conflicts(
        self,
        results: Tuple[TaskResult, ...],
    ) -> Tuple[TaskResult, ...]:
        """Detect and resolve conflicting task conclusions."""
        ...


@runtime_checkable
class ExecutionPlannerPort(Protocol):
    """Port for building DAG task execution graphs."""

    def build_plan(
        self,
        query_text: str,
        tasks: Tuple[AgentTask, ...],
    ) -> ExecutionPlan:
        """Construct ExecutionPlan."""
        ...
