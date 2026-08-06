"""Reflection Engine implementing ReflectionEnginePort."""

from ria.domain.agent.entities import ExecutionContext
from ria.domain.agent.value_objects import ReflectionResult
from ria.ports.agent.reflection import ReflectionEnginePort


class ReflectionEngine(ReflectionEnginePort):
    """Engine reflecting on intermediate task execution outputs."""

    def reflect(
        self,
        context: ExecutionContext,
    ) -> ReflectionResult:
        if not context.completed_tasks:
            return ReflectionResult(
                is_sufficient=False,
                recommended_action="execute_next",
                confidence_score=0.5,
                reasoning="No tasks completed yet.",
            )

        return ReflectionResult(
            is_sufficient=True,
            recommended_action="proceed_to_verification",
            confidence_score=0.95,
            reasoning="All planned tasks completed successfully.",
        )
