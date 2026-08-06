"""Agent Runtime implementing RuntimePort."""

from ria.domain.common.value_objects import UUIDv4
from ria.domain.agent.entities import ExecutionResult
from ria.domain.agent.value_objects import Goal
from ria.ports.agent.checkpoint import CheckpointManagerPort
from ria.ports.agent.executor import ExecutionEnginePort
from ria.ports.agent.planner import PlannerPort
from ria.ports.agent.reflection import ReflectionEnginePort
from ria.ports.agent.runtime import RuntimePort
from ria.ports.agent.tool_registry import ToolRegistryPort
from ria.ports.agent.verification import VerificationEnginePort


class AgentRuntime(RuntimePort):
    """Core Agent Runtime orchestrating complete goal lifecycle execution."""

    def __init__(
        self,
        planner: PlannerPort,
        executor: ExecutionEnginePort,
        tool_registry: ToolRegistryPort,
        reflection_engine: ReflectionEnginePort,
        verification_engine: VerificationEnginePort,
        checkpoint_manager: CheckpointManagerPort,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._tools = tool_registry
        self._reflection = reflection_engine
        self._verification = verification_engine
        self._checkpoints = checkpoint_manager

    def execute_goal(
        self,
        goal: Goal,
    ) -> ExecutionResult:
        res_id = UUIDv4.generate().value

        # 1. Create Execution Plan
        plan = self._planner.create_plan(goal)

        # 2. Execute Plan via Tool Registry & Execution Engine
        exec_ctx = self._executor.execute_plan(plan, self._tools)

        # 3. Create Checkpoint
        self._checkpoints.create_checkpoint(exec_ctx)

        # 4. Reflect on execution
        ref_res = self._reflection.reflect(exec_ctx)

        # 5. Verify completion
        ver_res = self._verification.verify(exec_ctx)

        is_success = ref_res.is_sufficient and ver_res.is_verified
        ans_text = f"Goal '{goal.description}' executed successfully. Reflected confidence: {ref_res.confidence_score:.2f}."

        return ExecutionResult(
            result_id=res_id,
            goal_id=goal.goal_id,
            is_success=is_success,
            answer_text=ans_text,
            reflection=ref_res,
            verification=ver_res,
        )
