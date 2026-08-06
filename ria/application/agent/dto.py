"""Data Transfer Objects for Agent Application Layer."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecuteGoalCommandDTO:
    """DTO requesting autonomous execution of a high-level engineering goal."""

    repo_id: str
    goal_description: str


@dataclass(frozen=True, slots=True)
class ResumeExecutionCommandDTO:
    """DTO requesting execution resumption from a checkpoint."""

    checkpoint_id: str


@dataclass(frozen=True, slots=True)
class CancelExecutionCommandDTO:
    """DTO requesting cancellation of an active execution session."""

    goal_id: str


@dataclass(frozen=True, slots=True)
class VerifyExecutionCommandDTO:
    """DTO requesting verification of an execution result."""

    goal_id: str
