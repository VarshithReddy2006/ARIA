"""Intent Analyzer implementing IntentAnalyzerPort."""

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.value_objects import IntentType
from ria.ports.knowledge.intent import IntentAnalyzerPort


class IntentAnalyzer(IntentAnalyzerPort):
    """Deterministic IntentAnalyzer classifying user questions into IntentType categories."""

    def analyze_intent(
        self,
        question: str,
        context: ContextPackage,
    ) -> IntentType:
        q_lower = question.lower()

        if any(w in q_lower for w in ("architecture", "design", "system structure")):
            return IntentType.ARCHITECTURE
        if any(w in q_lower for w in ("impact", "affected", "consequence")):
            return IntentType.IMPACT_ANALYSIS
        if any(w in q_lower for w in ("compare", "diff", "versus")):
            return IntentType.COMPARISON
        if any(w in q_lower for w in ("bug", "error", "issue", "fix")):
            return IntentType.BUG_INVESTIGATION
        if any(w in q_lower for w in ("refactor", "clean up", "simplify")):
            return IntentType.REFACTORING
        if any(w in q_lower for w in ("documentation", "docstring", "readme")):
            return IntentType.DOCUMENTATION
        if any(w in q_lower for w in ("flow", "how does", "sequence")):
            return IntentType.CODE_FLOW
        if any(w in q_lower for w in ("caller", "callee", "who calls")):
            return IntentType.CALL_GRAPH
        if any(w in q_lower for w in ("depend", "import", "package")):
            return IntentType.DEPENDENCY_ANALYSIS
        if any(w in q_lower for w in ("what is", "define", "where is")):
            return IntentType.DEFINITION

        return IntentType.IMPLEMENTATION_DETAILS
