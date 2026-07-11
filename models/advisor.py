"""AI Engineering Advisor (AEA) data models.

Defines the canonical schemas for AdvisorRecommendation, RoadmapPhase,
and AdvisorReport.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class AdvisorRecommendation(BaseModel):
    """A single consolidated, prioritized engineering recommendation."""

    id: str = Field(..., description="Unique identifier for this recommendation.")
    title: str = Field(..., description="Short, actionable title.")
    description: str = Field(
        ..., description="Full description of the issue and remediation approach."
    )
    category: str = Field(
        ...,
        description="Engineering category: security | architecture | performance | dependency | complexity | dead_code | documentation | testing | general.",
    )
    priority: str = Field(
        ..., description="Priority level: critical | high | medium | low."
    )
    estimated_effort: str = Field(
        "unknown", description="Human-readable effort estimate."
    )
    confidence: float = Field(
        1.0,
        description="Aggregate confidence across all contributing sources (0.0–1.0).",
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Platform layers that contributed this recommendation.",
    )
    affected_entities: List[str] = Field(
        default_factory=list, description="Files, symbols, or modules affected."
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Supporting evidence strings from originating sources.",
    )
    recurrence_count: int = Field(
        1,
        description="Number of monitoring runs in which this recommendation appeared.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional recommendation metadata."
    )


class RoadmapPhase(BaseModel):
    """A logical execution phase grouping related recommendations."""

    phase: int = Field(..., description="Phase number (1 = highest urgency).")
    title: str = Field(..., description="Human-readable phase title.")
    description: str = Field("", description="Summary of this phase's goals.")
    recommendations: List[AdvisorRecommendation] = Field(default_factory=list)
    estimated_total_effort: str = Field(
        "unknown", description="Aggregated effort for this phase."
    )


class AdvisorReport(BaseModel):
    """The complete output of the AI Engineering Advisor pipeline."""

    repository: str = Field(..., description="Repository owner/name.")
    generated_at: float = Field(..., description="Unix timestamp of report generation.")
    overall_priority: str = Field(
        "low", description="Highest priority level present in the recommendations."
    )
    recommendations: List[AdvisorRecommendation] = Field(default_factory=list)
    roadmap: List[RoadmapPhase] = Field(default_factory=list)
    statistics: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
