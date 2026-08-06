"""Execution Engine implementing ExecutionEnginePort."""

from ria.agent.execution_context import ExecutionContextManager
from ria.agent.scheduler import TaskScheduler
from ria.agent.task_graph import TaskGraphEngine
from ria.domain.agent.entities import ExecutionContext, Task
from ria.domain.agent.value_objects import ExecutionPlan, TaskStatus
from ria.ports.agent.executor import ExecutionEnginePort
from ria.ports.agent.tool_registry import ToolRegistryPort


class ExecutionEngine(ExecutionEnginePort):
    """Engine orchestrating task graph execution via ToolRegistryPort."""

    def __init__(
        self,
        graph_engine: TaskGraphEngine,
        scheduler: TaskScheduler,
        ctx_manager: ExecutionContextManager,
    ) -> None:
        self._graph_engine = graph_engine
        self._scheduler = scheduler
        self._ctx_manager = ctx_manager

    def execute_plan(
        self,
        plan: ExecutionPlan,
        tool_registry: ToolRegistryPort,
    ) -> ExecutionContext:
        ctx = self._ctx_manager.create_context(plan.goal)
        graph = self._graph_engine.build_graph(plan)

        # Update task statuses iteratively
        updated_tasks = list(graph.tasks)
        while True:
            ready_tasks = self._scheduler.get_ready_tasks(graph)
            if not ready_tasks:
                break

            for task in ready_tasks:
                t_idx = next(
                    i for i, t in enumerate(updated_tasks) if t.task_id == task.task_id
                )
                tool_exec = tool_registry.invoke_tool(
                    task.step.tool_name, task.step.parameters
                )

                status = (
                    TaskStatus.COMPLETED if tool_exec.is_success else TaskStatus.FAILED
                )
                completed_task = Task(
                    task_id=task.task_id,
                    step=task.step,
                    dependencies=task.dependencies,
                    status=status,
                    output=tool_exec.output,
                )
                updated_tasks[t_idx] = completed_task
                graph = graph.__class__(tasks=tuple(updated_tasks))

                ctx = self._ctx_manager.update_context(
                    ctx, task.task_id, tool_exec.output
                )

        return ctx
