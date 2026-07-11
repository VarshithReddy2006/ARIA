"""Autonomous Engineering Agent (AEA²) execution planning models.

Defines the canonical schemas for ExecutionTask, ExecutionBatch,
RollbackPoint, and ExecutionPlan.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionTask(BaseModel):
    """A discrete, reviewable unit of engineering work derived from an AdvisorRecommendation."""

    id: str = Field(..., description="Unique task identifier.")
    recommendation_id: str = Field(
        "", description="ID of the originating AdvisorRecommendation."
    )
    title: str = Field(..., description="Short, actionable task title.")
    description: str = Field("", description="Detailed task description.")
    category: str = Field(
        "general",
        description="Engineering category: security | architecture | performance | etc.",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="IDs of tasks that must complete before this one.",
    )
    parallel_with: List[str] = Field(
        default_factory=list, description="IDs of tasks that can run concurrently."
    )
    estimated_effort: str = Field("unknown", description="Estimated effort label.")
    risk: str = Field("low", description="Risk level: low | medium | high | critical.")
    risk_rationale: str = Field(
        "", description="Explanation of the assigned risk level."
    )
    affected_entities: List[str] = Field(
        default_factory=list, description="Files, modules, or symbols affected."
    )
    rollback_checkpoint: bool = Field(
        False, description="True if this task is a safe rollback point."
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionBatch(BaseModel):
    """A group of tasks that can be executed together in the same phase."""

    id: str = Field(..., description="Unique batch identifier.")
    order: int = Field(..., description="Execution order index (lower = earlier).")
    title: str = Field("", description="Human-readable batch title.")
    tasks: List[ExecutionTask] = Field(default_factory=list)
    parallel: bool = Field(
        False, description="True if tasks within this batch can be parallelized."
    )
    estimated_total_effort: str = Field("unknown")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConflictReport(BaseModel):
    """Documents a detected conflict between two execution tasks."""

    task_a_id: str
    task_b_id: str
    conflict_type: str = Field(
        ...,
        description="file_collision | module_ownership | migration_order | incompatible_sequence",
    )
    description: str = ""
    resolution: str = Field(
        "serialize",
        description="Recommended resolution: serialize | remove_one | manual_review",
    )


class ExecutionPlan(BaseModel):
    """The complete deterministic output of the AEA² execution planning pipeline."""

    id: str = Field(..., description="Unique plan identifier.")
    repository: str = Field(..., description="Repository owner/name.")
    generated_at: float = Field(..., description="Unix timestamp of plan generation.")
    advisor_report_timestamp: Optional[float] = Field(
        None, description="Timestamp of the source AdvisorReport."
    )
    batches: List[ExecutionBatch] = Field(default_factory=list)
    critical_path: List[str] = Field(
        default_factory=list,
        description="Ordered task IDs forming the longest dependency chain.",
    )
    rollback_points: List[str] = Field(
        default_factory=list,
        description="Task IDs designated as safe rollback checkpoints.",
    )
    conflicts: List[ConflictReport] = Field(
        default_factory=list,
        description="Detected task conflicts and their resolutions.",
    )
    statistics: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
