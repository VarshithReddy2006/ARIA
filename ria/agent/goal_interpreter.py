"""Goal Interpreter implementing GoalInterpreterPort."""

from ria.domain.common.value_objects import UUIDv4
from ria.domain.agent.value_objects import Goal, GoalType
from ria.ports.agent.goal import GoalInterpreterPort


class GoalInterpreter(GoalInterpreterPort):
    """Deterministic GoalInterpreter classifying natural language input into Goal entity."""

    def interpret_goal(
        self,
        raw_description: str,
        repo_id: str,
    ) -> Goal:
        gid = UUIDv4.generate().value
        desc_lower = raw_description.lower()

        if "architecture" in desc_lower or "structure" in desc_lower:
            gtype = GoalType.ARCHITECTURE_ANALYSIS
        elif "call" in desc_lower or "sequence" in desc_lower:
            gtype = GoalType.CALL_FLOW_ANALYSIS
        elif "depend" in desc_lower or "import" in desc_lower:
            gtype = GoalType.DEPENDENCY_INVESTIGATION
        elif "bug" in desc_lower or "fix" in desc_lower or "error" in desc_lower:
            gtype = GoalType.BUG_INVESTIGATION
        elif "doc" in desc_lower or "readme" in desc_lower:
            gtype = GoalType.DOCUMENTATION_GENERATION
        elif "refactor" in desc_lower:
            gtype = GoalType.REFACTORING_ANALYSIS
        elif "impact" in desc_lower or "affected" in desc_lower:
            gtype = GoalType.IMPACT_ANALYSIS
        elif "navigate" in desc_lower or "find" in desc_lower:
            gtype = GoalType.CODE_NAVIGATION
        elif "health" in desc_lower or "status" in desc_lower:
            gtype = GoalType.REPOSITORY_HEALTH
        else:
            gtype = GoalType.REPOSITORY_EXPLANATION

        return Goal(goal_id=gid, description=raw_description, goal_type=gtype, repo_id=repo_id)
