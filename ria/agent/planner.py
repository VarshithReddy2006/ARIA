"""Planner implementing PlannerPort."""

from ria.domain.common.value_objects import UUIDv4
from ria.domain.agent.value_objects import ExecutionPlan, ExecutionStep, Goal
from ria.ports.agent.planner import PlannerPort


class Planner(PlannerPort):
    """Deterministic Planner generating multi-step ExecutionPlan for goals."""

    def create_plan(
        self,
        goal: Goal,
    ) -> ExecutionPlan:
        pid = UUIDv4.generate().value

        s1 = ExecutionStep(step_id="step_1", tool_name="search_symbol", parameters={"repo_id": goal.repo_id, "query": goal.description})
        s2 = ExecutionStep(step_id="step_2", tool_name="find_definition", parameters={"repo_id": goal.repo_id, "symbol_moniker": ""})
        s3 = ExecutionStep(step_id="step_3", tool_name="build_context", parameters={"repo_id": goal.repo_id, "question": goal.description})
        s4 = ExecutionStep(step_id="step_4", tool_name="ask_repository", parameters={"repo_id": goal.repo_id, "question": goal.description})

        return ExecutionPlan(plan_id=pid, goal=goal, steps=(s1, s2, s3, s4))
