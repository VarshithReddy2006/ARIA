"""Task Scheduler."""

from typing import List

from ria.domain.agent.entities import Task, TaskGraph
from ria.domain.agent.value_objects import TaskStatus


class TaskScheduler:
    """Scheduler identifying tasks in TaskGraph ready for execution."""

    def get_ready_tasks(self, graph: TaskGraph) -> List[Task]:
        completed_ids = {
            t.task_id.value for t in graph.tasks if t.status == TaskStatus.COMPLETED
        }
        ready: list[Task] = []

        for task in graph.tasks:
            if task.status == TaskStatus.PENDING:
                dep_ids = {dep.value for dep in task.dependencies}
                if dep_ids.issubset(completed_ids):
                    ready.append(task)

        return ready
