"""Runtime-checkable public contracts for the agent platform."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaskPlannerPort(Protocol):
    def plan_tasks(self, query_text: str, context: Any) -> Any: ...


@runtime_checkable
class AgentRegistryPort(Protocol):
    def get_agent_definition(self, agent_id: Any) -> Any: ...
    def list_agent_definitions(self) -> tuple[Any, ...]: ...


@runtime_checkable
class AgentFactoryPort(Protocol):
    def create_agent(self, definition: Any) -> Any: ...


@runtime_checkable
class AgentLifecyclePort(Protocol):
    def transition_state(self, agent_id: Any, new_state: Any) -> Any: ...
    def terminate_agent(self, agent_id: Any) -> None: ...


@runtime_checkable
class AgentOrchestratorPort(Protocol):
    def execute_plan(self, session: Any, shared_context: Any) -> Any: ...


@runtime_checkable
class SharedContextPort(Protocol):
    def get_context(self) -> Any: ...
    def update_context(self, prompt_context: Any) -> Any: ...


@runtime_checkable
class CommunicationBusPort(Protocol):
    def publish(self, message: Any) -> None: ...
    def subscribe(self, recipient_id: Any) -> Any: ...


@runtime_checkable
class ResultAggregatorPort(Protocol):
    def aggregate_results(self, session_id: str, task_results: tuple[Any, ...]) -> Any: ...


@runtime_checkable
class ConflictResolutionPort(Protocol):
    def resolve_conflicts(self, results: tuple[Any, ...]) -> tuple[Any, ...]: ...


@runtime_checkable
class ExecutionPlannerPort(Protocol):
    def build_plan(self, query_text: str, tasks: tuple[Any, ...]) -> Any: ...
