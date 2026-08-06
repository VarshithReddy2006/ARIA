"""Tool Selector."""

from typing import List

from ria.domain.agent.value_objects import GoalType


class ToolSelector:
    """Selector choosing appropriate tools based on GoalType."""

    def select_tools_for_goal(self, goal_type: GoalType) -> List[str]:
        if goal_type == GoalType.ARCHITECTURE_ANALYSIS:
            return [
                "search_symbol",
                "find_dependencies",
                "build_context",
                "ask_repository",
            ]
        if goal_type == GoalType.CALL_FLOW_ANALYSIS:
            return ["search_symbol", "find_callers", "find_callees", "ask_repository"]
        if goal_type == GoalType.DEPENDENCY_INVESTIGATION:
            return ["find_dependencies", "build_context", "ask_repository"]
        return ["search_symbol", "find_definition", "build_context", "ask_repository"]
