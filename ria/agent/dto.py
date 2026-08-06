"""Data Transfer Objects for Agent Subsystem."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ExecuteGoalDTO:
    """DTO requesting execution of a high-level goal."""

    repo_id: str
    goal_description: str


@dataclass(frozen=True, slots=True)
class AgentResultDTO:
    """DTO summarizing goal execution response."""

    goal_id: str
    is_success: bool
    answer_text: str
    total_tasks: int
    elapsed_ms: float
    error_message: Optional[str] = None
