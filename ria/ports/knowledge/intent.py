"""Intent Analyzer Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.value_objects import IntentType


@runtime_checkable
class IntentAnalyzerPort(Protocol):
    """Protocol for determining intent category for a user question and context."""

    def analyze_intent(
        self,
        question: str,
        context: ContextPackage,
    ) -> IntentType:
        """Classify user question into IntentType."""
        ...
