"""Engineering Memory data models.

Defines Pydantic structures for Repository Snapshots, Repository Events,
Timelines, Trend Metrics, and the Memory Context.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class RepositorySnapshot(BaseModel):
    """An immutable, facts-only record of a repository's state at a point in time."""

    snapshot_id: str = Field(..., description="Unique snapshot identifier (e.g. repo_name_commit_sha).")
    repository: str = Field(..., description="Repository owner/name.")
    timestamp: float = Field(..., description="Unix timestamp of snapshot creation.")
    commit_sha: str = Field(..., description="Commit SHA associated with the snapshot.")
    branch: str = Field(..., description="Git branch name.")
    analysis_version: str = Field(..., description="Version of the analysis system.")
    digital_twin_reference: str = Field(..., description="Reference metadata identifier for the digital twin.")
    knowledge_graph_reference: str = Field(..., description="Reference metadata identifier for the knowledge graph.")
    health_reference: str = Field(..., description="Reference identifier for health details.")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Aggregated metrics (complexity, symbol count, files, etc.).")


class RepositoryEvent(BaseModel):
    """A granular, immutable record of a single structural change in the repository."""

    event_id: str = Field(..., description="Unique identifier for the event.")
    repository: str = Field(..., description="Repository owner/name.")
    timestamp: float = Field(..., description="Unix timestamp of the event.")
    commit_sha: str = Field(..., description="Commit SHA introducing the event.")
    event_type: str = Field(..., description="FileAdded | FileRemoved | FileModified | SymbolAdded | SymbolRemoved | DependencyAdded | DependencyRemoved | ArchitectureChanged | HealthChanged | ComplianceChanged | ComplexityChanged")
    affected_entity: str = Field(..., description="Target file path, symbol name, or dependency ID.")
    previous_state: Optional[Any] = Field(None, description="Previous state or value.")
    current_state: Optional[Any] = Field(None, description="Current state or value.")
    severity: str = Field("info", description="Change severity: info | warning | critical.")
    confidence: float = Field(1.0, description="Confidence score (0.0-1.0).")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra event properties.")


class RepositoryTimeline(BaseModel):
    """A chronological view of snapshots and repository events."""

    repository: str = Field(..., description="Repository owner/name.")
    snapshots: List[RepositorySnapshot] = Field(default_factory=list, description="Immutable snapshots chronologically ordered.")
    events: List[RepositoryEvent] = Field(default_factory=list, description="Chronological list of change events.")


class TrendMetric(BaseModel):
    """A structured analysis of a specific metric trend over time."""

    metric_name: str = Field(..., description="Name of the evaluated metric (e.g. complexity, health_score).")
    direction: str = Field(..., description="Linear direction: Increasing | Decreasing | Stable.")
    velocity: str = Field(..., description="Rate of change: High | Medium | Low.")
    volatility: str = Field(..., description="Variability: High | Medium | Low.")
    confidence: float = Field(..., description="Confidence rating (0.0-1.0).")


class MemoryContext(BaseModel):
    """A scoped, policy-bounded view of Engineering Memory history."""

    policy: str = Field("recent_history", description="recent_history | architecture_history | dependency_history | compliance_history")
    snapshots: List[RepositorySnapshot] = Field(default_factory=list)
    timeline: RepositoryTimeline = Field(...)
    trend_metrics: List[TrendMetric] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    """The result of comparing two snapshots or commit states."""

    previous_commit: str = Field(..., description="Baseline commit SHA.")
    current_commit: str = Field(..., description="Target commit SHA.")
    changes: List[RepositoryEvent] = Field(default_factory=list, description="Detected changes.")
    health_delta: float = Field(0.0, description="Health score change.")
    dependency_delta: int = Field(0, description="Change in dependencies count.")
