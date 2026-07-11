"""Continuous Repository Monitoring (CRM) data models.

Defines Pydantic schemas for MonitoringRun, RepositoryHealthTrend, and MonitoringStatus.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MonitoringRun(BaseModel):
    """An immutable record of a single monitoring execution."""

    id: str = Field(..., description="Unique identifier for this monitoring run.")
    repository: str = Field(..., description="Repository owner/name.")
    timestamp: float = Field(..., description="Unix timestamp when the run started.")
    trigger: str = Field(
        ...,
        description="What triggered this run: indexing | manual | commit_threshold | time_based.",
    )
    policy: str = Field(..., description="Policy name that authorized the run.")
    inspection_report_path: str = Field(
        ..., description="Filesystem path reference to the persisted InspectionReport."
    )
    status: str = Field(..., description="completed | failed | skipped.")
    duration_ms: float = Field(
        0.0, description="Total duration of the monitoring run in milliseconds."
    )
    overall_score: float = Field(
        100.0, description="Overall health score from the associated InspectionReport."
    )
    finding_counts: Dict[str, int] = Field(
        default_factory=dict, description="Finding counts by severity."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional run metadata."
    )


class RepositoryHealthTrend(BaseModel):
    """A deterministic time-series view of repository health across monitoring runs."""

    repository: str = Field(..., description="Repository owner/name.")
    timestamps: List[float] = Field(
        default_factory=list, description="Timestamps of scored monitoring runs."
    )
    overall_scores: List[float] = Field(
        default_factory=list, description="Overall health scores per run."
    )
    architecture_scores: List[float] = Field(
        default_factory=list, description="Architecture-category scores per run."
    )
    security_scores: List[float] = Field(
        default_factory=list, description="Security-category scores per run."
    )
    maintainability_scores: List[float] = Field(
        default_factory=list,
        description="Maintainability (complexity+docs+testing) scores per run.",
    )
    trend: str = Field(
        "stable", description="Linear trend direction: Improving | Degrading | Stable."
    )
    confidence: float = Field(
        1.0, description="Confidence in the trend calculation (0.0–1.0)."
    )


class MonitoringStatus(BaseModel):
    """A lightweight summary of the current monitoring state for a repository."""

    repository: str = Field(..., description="Repository owner/name.")
    total_runs: int = Field(0, description="Total number of monitoring runs completed.")
    last_run_timestamp: Optional[float] = Field(
        None, description="Timestamp of the most recent run."
    )
    last_run_status: Optional[str] = Field(
        None, description="Status of the most recent run."
    )
    last_overall_score: Optional[float] = Field(
        None, description="Most recent overall health score."
    )
    current_trend: Optional[str] = Field(
        None, description="Current health trend direction."
    )
    active_policy: str = Field(
        "immediate", description="Active monitoring policy name."
    )
