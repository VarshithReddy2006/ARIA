"""Multi-Agent Platform application services and facade (Phases 11 & 13).

Provides unified application services: AgentPlatformService, ExecutionService, TaskPlanningService,
AgentManagementService, AggregationService, with full metrics sink observability.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from ria.application.agent_lifecycle import AgentLifecycleService
from ria.application.agent_orchestrator import AgentOrchestratorService
from ria.application.agent_registry import AgentRegistryService
from ria.application.communication_bus import AgentCommunicationBusService
from ria.application.conflict_resolution import ConflictResolutionService
from ria.application.result_aggregator import ResultAggregatorService
from ria.application.shared_context_manager import SharedContextManagerService
from ria.application.task_planner import TaskPlannerService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.agent_definition import AgentDefinition
from ria.domain.models.agent_execution import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionSession,
    SharedContext,
)
from ria.domain.models.agent_result import ExecutionReport
from ria.domain.models.agent_task import TaskResult
from ria.domain.models.prompt_context import PromptContext
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.reasoning import ReasoningEnginePort

__all__ = [
    "AgentPlatformService",
    "ExecutionService",
    "TaskPlanningService",
    "AgentManagementService",
    "AggregationService",
]


class TaskPlanningService:
    """Service wrapping task planning."""

    def __init__(self, planner: TaskPlannerService) -> None:
        self._planner = planner

    def plan(self, query_text: str, context: ExecutionContext) -> ExecutionPlan:
        return self._planner.plan_tasks(query_text, context)


class AgentManagementService:
    """Service wrapping agent registry and lifecycle management."""

    def __init__(
        self, registry: AgentRegistryService, lifecycle: AgentLifecycleService
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle

    def list_agents(self) -> Tuple[AgentDefinition, ...]:
        return self._registry.list_agent_definitions()


class AggregationService:
    """Service wrapping conflict resolution and result aggregation."""

    def __init__(
        self,
        conflict_resolver: ConflictResolutionService,
        aggregator: ResultAggregatorService,
    ) -> None:
        self._conflict_resolver = conflict_resolver
        self._aggregator = aggregator

    def aggregate(
        self, session_id: str, task_results: Tuple[TaskResult, ...]
    ) -> ExecutionReport:
        resolved = self._conflict_resolver.resolve_conflicts(task_results)
        return self._aggregator.aggregate_results(session_id, resolved)


class ExecutionService:
    """Service wrapping plan execution."""

    def __init__(self, orchestrator: AgentOrchestratorService) -> None:
        self._orchestrator = orchestrator

    def execute(
        self, session: ExecutionSession, shared_context: SharedContext
    ) -> ExecutionReport:
        return self._orchestrator.execute_plan(session, shared_context)


class AgentPlatformService:
    """Facade application service orchestrating end-to-end multi-agent execution with observability."""

    def __init__(
        self,
        reasoning_engine: Optional[ReasoningEnginePort] = None,
        metrics_sink: Optional[MetricsSink] = None,
    ) -> None:
        self._metrics_sink = metrics_sink or NullMetricsSink()

        self._planner = TaskPlannerService()
        self._registry = AgentRegistryService()
        self._lifecycle = AgentLifecycleService()
        self._orchestrator = AgentOrchestratorService(
            reasoning_engine=reasoning_engine,
            registry=self._registry,
            lifecycle=self._lifecycle,
        )
        self._context_manager = SharedContextManagerService()
        self._bus = AgentCommunicationBusService()
        self._conflict_resolver = ConflictResolutionService()
        self._aggregator = ResultAggregatorService()

    def run_platform(
        self,
        query_text: str,
        repository_id: RepositoryId,
        commit_sha: CommitSha,
        prompt_context: PromptContext,
    ) -> ExecutionReport:
        """Run multi-agent platform for a user query."""
        t0 = time.perf_counter()

        ctx = ExecutionContext(repository_id=repository_id, commit_sha=commit_sha)

        # 1. Plan Tasks
        t_plan = time.perf_counter()
        plan = self._planner.plan_tasks(query_text, ctx)
        self._metrics_sink.observe(
            "ria.agent.planning_seconds", time.perf_counter() - t_plan
        )

        session = ExecutionSession(session_id=plan.plan_id, context=ctx, plan=plan)

        # 2. Shared Context
        shared_ctx = self._context_manager.update_context(prompt_context)

        # 3. Execute Tasks via Orchestrator
        t_exec = time.perf_counter()
        raw_report = self._orchestrator.execute_plan(session, shared_ctx)
        self._metrics_sink.observe(
            "ria.agent.execution_seconds", time.perf_counter() - t_exec
        )

        # 4. Resolve Conflicts & Aggregate Results
        t_agg = time.perf_counter()
        final_report = self._aggregator.aggregate_results(
            session_id=session.session_id,
            task_results=self._conflict_resolver.resolve_conflicts(
                raw_report.task_results
            ),
        )
        self._metrics_sink.observe(
            "ria.agent.aggregation_seconds", time.perf_counter() - t_agg
        )

        total_elapsed = time.perf_counter() - t0
        self._metrics_sink.observe("ria.agent.total_seconds", total_elapsed)
        self._metrics_sink.increment("ria.agent.sessions_total")

        return final_report
