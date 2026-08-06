"""Task Graph Engine."""

from ria.domain.agent.entities import Task, TaskGraph
from ria.domain.agent.value_objects import ExecutionPlan, TaskId, TaskStatus


class TaskGraphEngine:
    """Engine constructing TaskGraph DAG from ExecutionPlan."""

    def build_graph(self, plan: ExecutionPlan) -> TaskGraph:
        tasks: list[Task] = []
        prev_tid: tuple[TaskId, ...] = ()

        for idx, step in enumerate(plan.steps):
            tid = TaskId(value=f"task_{idx + 1}")
            t = Task(
                task_id=tid, step=step, dependencies=prev_tid, status=TaskStatus.PENDING
            )
            tasks.append(t)
            prev_tid = (tid,)

        return TaskGraph(tasks=tuple(tasks))
