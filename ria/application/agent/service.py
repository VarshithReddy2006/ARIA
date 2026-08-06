"""Application Service for Agent Runtime."""

from ria.agent.dto import AgentResultDTO
from ria.agent.runtime import AgentRuntime
from ria.application.agent.dto import ExecuteGoalCommandDTO
from ria.ports.agent.goal import GoalInterpreterPort
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.sync.registry import RepositoryRegistryPort


class AgentApplicationService:
    """Application Service coordinating repository state lookup and AgentRuntime execution."""

    def __init__(
        self,
        runtime: AgentRuntime,
        goal_interpreter: GoalInterpreterPort,
        registry: RepositoryRegistryPort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._runtime = runtime
        self._interpreter = goal_interpreter
        self._registry = registry
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def execute_goal(self, dto: ExecuteGoalCommandDTO) -> AgentResultDTO:
        start_t = self._clock.monotonic_seconds()
        self._logger.info(
            "Executing AgentApplicationService.execute_goal", repo_id=dto.repo_id
        )

        st = next(
            (
                s
                for s in self._registry.list_all()
                if s.identity.repo_id.value == dto.repo_id
            ),
            None,
        )
        if st is None or st.current_commit is None:
            return AgentResultDTO(
                goal_id="none",
                is_success=False,
                answer_text="",
                total_tasks=0,
                elapsed_ms=0.0,
                error_message=f"Repository '{dto.repo_id}' is not registered or synchronized.",
            )

        try:
            # 1. Interpret goal
            goal = self._interpreter.interpret_goal(dto.goal_description, dto.repo_id)

            # 2. Execute via AgentRuntime
            result = self._runtime.execute_goal(goal)

            elapsed = (self._clock.monotonic_seconds() - start_t) * 1000.0
            self._metrics.record_duration("agent_execute_goal_ms", elapsed)

            return AgentResultDTO(
                goal_id=result.goal_id,
                is_success=result.is_success,
                answer_text=result.answer_text,
                total_tasks=4,
                elapsed_ms=elapsed,
            )
        except Exception as err:
            elapsed = (self._clock.monotonic_seconds() - start_t) * 1000.0
            self._logger.error(
                "Agent goal execution failed", exc=err, repo_id=dto.repo_id
            )
            return AgentResultDTO(
                goal_id="none",
                is_success=False,
                answer_text="",
                total_tasks=0,
                elapsed_ms=elapsed,
                error_message=str(err),
            )
