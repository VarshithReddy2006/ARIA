"""Knowledge Reasoning Planner."""

from ria.domain.knowledge.value_objects import IntentType, ReasoningPolicy


class KnowledgePlanner:
    """Planner creating reasoning policies for different intent categories."""

    def create_policy(self, intent: IntentType) -> ReasoningPolicy:
        if intent in (
            IntentType.ARCHITECTURE,
            IntentType.REFACTORING,
            IntentType.BUG_INVESTIGATION,
        ):
            return ReasoningPolicy(temperature=0.2, max_tokens=2500)
        return ReasoningPolicy(temperature=0.1, max_tokens=1500)
