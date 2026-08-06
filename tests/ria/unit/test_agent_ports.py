"""Unit tests for Phase 2 agent ports runtime conformance."""

from __future__ import annotations

from typing import Iterator, Optional, Tuple

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
from ria.ports.agent import (
    AgentFactoryPort,
    AgentLifecyclePort,
    AgentOrchestratorPort,
    AgentRegistryPort,
    CommunicationBusPort,
    ConflictResolutionPort,
    ExecutionPlannerPort,
    ResultAggregatorPort,
    SharedContextPort,
    TaskPlannerPort,
)


class DummyTaskPlanner:
    def plan_tasks(self, query_text: str, context: ExecutionContext) -> ExecutionPlan:
        return ExecutionPlan(plan_id="mock")


class DummyAgentRegistry:
    def get_agent_definition(self, agent_id: AgentId) -> Optional[AgentDefinition]:
        return None

    def list_agent_definitions(self) -> Tuple[AgentDefinition, ...]:
        return ()


class DummyAgentFactory:
    def create_agent(self, definition: AgentDefinition) -> AgentId:
        return definition.agent_id


class DummyAgentLifecycle:
    def transition_state(self, agent_id: AgentId, new_state: AgentState) -> AgentState:
        return new_state

    def terminate_agent(self, agent_id: AgentId) -> None:
        pass


class DummyAgentOrchestrator:
    def execute_plan(
        self, session: ExecutionSession, shared_context: SharedContext
    ) -> ExecutionReport:
        return ExecutionReport(session_id=session.session_id, summary_text="mock")


class DummySharedContextManager:
    def get_context(self) -> SharedContext:
        return SharedContext(prompt_context=PromptContext())

    def update_context(self, prompt_context: PromptContext) -> SharedContext:
        return SharedContext(prompt_context=prompt_context)


class DummyCommunicationBus:
    def publish(self, message: AgentMessage) -> None:
        pass

    def subscribe(self, recipient_id: AgentId) -> Iterator[AgentMessage]:
        return iter(())


class DummyResultAggregator:
    def aggregate_results(
        self, session_id: str, task_results: Tuple[TaskResult, ...]
    ) -> ExecutionReport:
        return ExecutionReport(session_id=session_id, summary_text="mock")


class DummyConflictResolution:
    def resolve_conflicts(
        self, results: Tuple[TaskResult, ...]
    ) -> Tuple[TaskResult, ...]:
        return results


class DummyExecutionPlanner:
    def build_plan(
        self, query_text: str, tasks: Tuple[AgentTask, ...]
    ) -> ExecutionPlan:
        return ExecutionPlan(plan_id="mock")


def test_agent_ports_conformance() -> None:
    assert isinstance(DummyTaskPlanner(), TaskPlannerPort)
    assert isinstance(DummyAgentRegistry(), AgentRegistryPort)
    assert isinstance(DummyAgentFactory(), AgentFactoryPort)
    assert isinstance(DummyAgentLifecycle(), AgentLifecyclePort)
    assert isinstance(DummyAgentOrchestrator(), AgentOrchestratorPort)
    assert isinstance(DummySharedContextManager(), SharedContextPort)
    assert isinstance(DummyCommunicationBus(), CommunicationBusPort)
    assert isinstance(DummyResultAggregator(), ResultAggregatorPort)
    assert isinstance(DummyConflictResolution(), ConflictResolutionPort)
    assert isinstance(DummyExecutionPlanner(), ExecutionPlannerPort)
