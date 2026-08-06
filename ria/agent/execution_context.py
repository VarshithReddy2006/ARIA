"""Execution Context Manager."""

from typing import Any, Dict

from ria.domain.common.value_objects import UUIDv4
from ria.domain.agent.entities import ExecutionContext
from ria.domain.agent.value_objects import Goal, TaskId


class ExecutionContextManager:
    """Manager initializing and updating ExecutionContext state."""

    def create_context(self, goal: Goal) -> ExecutionContext:
        cid = UUIDv4.generate().value
        return ExecutionContext(
            context_id=cid, goal=goal, completed_tasks=(), intermediate_outputs={}
        )

    def update_context(
        self, context: ExecutionContext, completed_task: TaskId, output: Dict[str, Any]
    ) -> ExecutionContext:
        new_completed = tuple(list(context.completed_tasks) + [completed_task])
        new_outputs = dict(context.intermediate_outputs)
        new_outputs[completed_task.value] = output

        return ExecutionContext(
            context_id=context.context_id,
            goal=context.goal,
            completed_tasks=new_completed,
            intermediate_outputs=new_outputs,
        )
