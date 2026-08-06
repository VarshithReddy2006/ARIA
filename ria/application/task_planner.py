"""Task Planner application service.

Decomposes user request queries into a DAG task execution plan.
Implements :class:`~ria.ports.agent.TaskPlannerPort` and :class:`~ria.ports.agent.ExecutionPlannerPort`.
"""

from __future__ import annotations

import hashlib
from typing import List, Tuple

from ria.domain.models.agent_execution import ExecutionContext, ExecutionPlan
from ria.domain.models.agent_task import AgentTask, TaskDependency, TaskPlan
from ria.domain.models.task_id import TaskId
from ria.ports.agent import ExecutionPlannerPort, TaskPlannerPort

__all__ = ["TaskPlannerService"]


class TaskPlannerService(TaskPlannerPort, ExecutionPlannerPort):
    """Service for decomposing user queries into structured multi-agent task execution plans."""

    def plan_tasks(
        self,
        query_text: str,
        context: ExecutionContext,
    ) -> ExecutionPlan:
        """Decompose query into a DAG of AgentTasks."""
        q_lower = query_text.lower()
        tasks: List[AgentTask] = []
        deps: List[TaskDependency] = []

        # 1. Primary analysis task
        tid_analyst = TaskId.for_task("analysis", "repository_analysis")
        t_analyst = AgentTask(
            task_id=tid_analyst,
            title="Repository Analysis",
            description=f"Analyze repository structure and symbols for: {query_text}",
            plan=TaskPlan(task_type="analysis", priority=1),
        )
        tasks.append(t_analyst)

        # 2. Specialized sub-tasks based on query intent
        if "depend" in q_lower or "import" in q_lower:
            tid_dep = TaskId.for_task("dependency", "dependency_analysis")
            t_dep = AgentTask(
                task_id=tid_dep,
                title="Dependency Analysis",
                description="Analyze module dependencies and imports",
                plan=TaskPlan(task_type="dependency", priority=2),
                dependencies=(tid_analyst,),
            )
            tasks.append(t_dep)
            deps.append(
                TaskDependency(parent_task_id=tid_analyst, child_task_id=tid_dep)
            )

        if "security" in q_lower or "vulnerab" in q_lower:
            tid_sec = TaskId.for_task("security", "security_review")
            t_sec = AgentTask(
                task_id=tid_sec,
                title="Security Review",
                description="Inspect code for security patterns and risk areas",
                plan=TaskPlan(task_type="security", priority=2),
                dependencies=(tid_analyst,),
            )
            tasks.append(t_sec)
            deps.append(
                TaskDependency(parent_task_id=tid_analyst, child_task_id=tid_sec)
            )

        # Default secondary review task if no specialized intent matched
        if len(tasks) == 1:
            tid_rev = TaskId.for_task("review", "code_review")
            t_rev = AgentTask(
                task_id=tid_rev,
                title="Code Review",
                description="Perform comprehensive code review",
                plan=TaskPlan(task_type="review", priority=2),
                dependencies=(tid_analyst,),
            )
            tasks.append(t_rev)
            deps.append(
                TaskDependency(parent_task_id=tid_analyst, child_task_id=tid_rev)
            )

        plan_digest = hashlib.sha256(
            f"{query_text}:{context.commit_sha}".encode("utf-8")
        ).hexdigest()[:16]

        return ExecutionPlan(
            plan_id=f"plan_{plan_digest}",
            tasks=tuple(tasks),
            dependencies=tuple(deps),
        )

    def build_plan(
        self,
        query_text: str,
        tasks: Tuple[AgentTask, ...],
    ) -> ExecutionPlan:
        """Construct ExecutionPlan directly from explicit tasks."""
        deps: List[TaskDependency] = []
        for t in tasks:
            for parent in t.dependencies:
                deps.append(
                    TaskDependency(parent_task_id=parent, child_task_id=t.task_id)
                )

        digest = hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:16]
        return ExecutionPlan(
            plan_id=f"plan_{digest}",
            tasks=tasks,
            dependencies=tuple(deps),
        )
