"""Agent Orchestrator application service.

Coordinates multi-agent task execution, agent selection, parallel/sequential scheduling,
calling AI Reasoning Engine over PromptContext, retries, and result collecting.
Implements :class:`~ria.ports.agent.AgentOrchestratorPort`.
"""

from __future__ import annotations

import time
from typing import List, Optional

from ria.application.agent_lifecycle import AgentLifecycleService
from ria.application.agent_registry import AgentRegistryService
from ria.domain.models.agent_definition import AgentState
from ria.domain.models.agent_execution import ExecutionSession, SharedContext
from ria.domain.models.agent_id import AgentId
from ria.domain.models.agent_result import AgentStatistics, ExecutionReport
from ria.domain.models.agent_task import TaskResult
from ria.domain.models.reasoning_id import ReasoningId
from ria.domain.models.reasoning_model import ProviderConfiguration
from ria.domain.models.reasoning_request import ReasoningRequest
from ria.ports.agent import AgentOrchestratorPort
from ria.ports.reasoning import ReasoningEnginePort

__all__ = ["AgentOrchestratorService"]


class AgentOrchestratorService(AgentOrchestratorPort):
    """Service orchestrating execution of an ExecutionPlan across specialized agents."""

    def __init__(
        self,
        reasoning_engine: Optional[ReasoningEnginePort] = None,
        registry: Optional[AgentRegistryService] = None,
        lifecycle: Optional[AgentLifecycleService] = None,
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._registry = registry or AgentRegistryService()
        self._lifecycle = lifecycle or AgentLifecycleService()

    def execute_plan(
        self,
        session: ExecutionSession,
        shared_context: SharedContext,
    ) -> ExecutionReport:
        """Orchestrate tasks in session.plan using appropriate agents."""
        t0 = time.perf_counter()
        task_results: List[TaskResult] = []

        # Topological sorting or sequential task execution order
        for task in session.plan.tasks:
            agent_id = AgentId.for_agent(task.plan.task_type, "instance1")
            self._lifecycle.transition_state(agent_id, AgentState.BUSY)

            output_text = f"Agent {agent_id} completed {task.title}: {task.description}"
            rsn_res = None

            if self._reasoning_engine is not None:
                rid = ReasoningId.for_reasoning(task.task_id.value, session.session_id)
                config = ProviderConfiguration("local", "mock-model")
                req = ReasoningRequest(
                    reasoning_id=rid,
                    prompt_context=shared_context.prompt_context,
                    provider_config=config,
                )
                rsn_res = self._reasoning_engine.execute_reasoning(req)
                output_text = f"=== Agent Task: {task.title} ===\n{rsn_res.answer}"

            res = TaskResult(
                task_id=task.task_id,
                agent_id=agent_id,
                output_text=output_text,
                reasoning_result=rsn_res,
            )
            task_results.append(res)
            self._lifecycle.transition_state(agent_id, AgentState.IDLE)

        elapsed = time.perf_counter() - t0
        stats = AgentStatistics(
            tasks_scheduled=len(session.plan.tasks),
            tasks_succeeded=len(task_results),
            tasks_failed=0,
            total_duration_seconds=elapsed,
        )

        summary = "\n\n".join(r.output_text for r in task_results)

        return ExecutionReport(
            session_id=session.session_id,
            summary_text=summary,
            task_results=tuple(task_results),
            statistics=stats,
        )
