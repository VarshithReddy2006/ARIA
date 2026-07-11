"""Intelligent IDE Workspace data models.

Defines workspace state and the panel DTOs used by each workspace module.
These are pure presentation models — they carry no analysis logic.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core workspace state
# ---------------------------------------------------------------------------


class WorkspaceState(BaseModel):
    """Represents the current interactive state of a developer's workspace session."""

    repository: str = Field(..., description="Repository owner/name.")
    selected_file: Optional[str] = Field(
        None, description="File currently focused in the editor."
    )
    selected_symbol: Optional[str] = Field(
        None, description="Symbol (function, class, etc.) under focus."
    )
    active_panel: str = Field(
        "overview", description="Which workspace panel is currently active."
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict, description="Active filters per panel."
    )
    ui_preferences: Dict[str, Any] = Field(
        default_factory=dict, description="User UI preferences."
    )


# ---------------------------------------------------------------------------
# Panel DTOs (one per workspace module)
# ---------------------------------------------------------------------------


class HealthSummary(BaseModel):
    """Compact health snapshot surfaced in multiple panels."""

    overall_score: Optional[float] = None
    overall_priority: Optional[str] = None
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    trend_direction: Optional[str] = None


class OverviewPanel(BaseModel):
    """Repository Overview panel — Digital Twin + health summary."""

    repository: str
    description: Optional[str] = None
    primary_language: Optional[str] = None
    languages: List[str] = Field(default_factory=list)
    total_files: int = 0
    total_symbols: int = 0
    architecture_style: Optional[str] = None
    dependency_count: int = 0
    health: HealthSummary = Field(default_factory=HealthSummary)
    last_indexed_at: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExplorerNode(BaseModel):
    """A single navigable node in the Repository Explorer."""

    id: str
    label: str
    kind: str = Field("module", description="module | symbol | dependency | file")
    children: List["ExplorerNode"] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


ExplorerNode.model_rebuild()


class ExplorerPanel(BaseModel):
    """Repository Explorer panel — Knowledge Graph navigation."""

    repository: str
    total_nodes: int = 0
    total_edges: int = 0
    root_nodes: List[ExplorerNode] = Field(default_factory=list)
    entry_points: List[str] = Field(
        default_factory=list, description="Primary module entry points."
    )
    dependency_summary: Dict[str, int] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatSessionMeta(BaseModel):
    """Engineering Chat panel metadata — Graph-RAG session info."""

    repository: str
    grounding_available: bool = True
    context_nodes: int = 0
    suggested_questions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FindingsSummary(BaseModel):
    """A lightweight finding entry for the Findings panel."""

    id: str
    title: str
    category: str
    severity: str
    confidence: float
    affected_entities: List[str] = Field(default_factory=list)
    recommendation_count: int = 0


class FindingsPanel(BaseModel):
    """Engineering Findings panel — ARI findings display."""

    repository: str
    total_findings: int = 0
    findings: List[FindingsSummary] = Field(default_factory=list)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_category: Dict[str, int] = Field(default_factory=dict)
    last_inspected_at: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TimelineEntry(BaseModel):
    """A single snapshot entry in the Repository Timeline panel."""

    snapshot_id: str
    timestamp: float
    commit_hash: Optional[str] = None
    summary: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)


class TimelinePanel(BaseModel):
    """Repository Timeline panel — Engineering Memory evolution display."""

    repository: str
    snapshot_count: int = 0
    timeline: List[TimelineEntry] = Field(default_factory=list)
    trends: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MonitorPanel(BaseModel):
    """Monitoring Dashboard panel — CRM status display."""

    repository: str
    status: str = "unknown"
    last_run_at: Optional[float] = None
    last_trigger: Optional[str] = None
    run_count: int = 0
    health_trend: Optional[str] = None
    overall_health_score: Optional[float] = None
    recent_runs: List[Dict[str, Any]] = Field(default_factory=list)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AdvisorPanel(BaseModel):
    """Advisor Dashboard panel — AEA recommendation display."""

    repository: str
    overall_priority: str = "low"
    total_recommendations: int = 0
    top_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    roadmap_phases: int = 0
    roadmap_summary: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BatchSummary(BaseModel):
    """A lightweight batch entry for the Execution panel."""

    batch_id: str
    order: int
    title: str
    task_count: int
    parallel: bool
    estimated_effort: str


class ExecutionPanel(BaseModel):
    """Execution Planner panel — AEA² plan visualization."""

    repository: str
    total_tasks: int = 0
    total_batches: int = 0
    critical_path_length: int = 0
    rollback_checkpoints: int = 0
    conflict_count: int = 0
    overall_risk: str = "low"
    batches: List[BatchSummary] = Field(default_factory=list)
    critical_path: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceSnapshot(BaseModel):
    """Complete workspace payload returned by the root workspace endpoint."""

    state: WorkspaceState
    overview: Optional[OverviewPanel] = None
    explorer: Optional[ExplorerPanel] = None
    chat: Optional[ChatSessionMeta] = None
    findings: Optional[FindingsPanel] = None
    timeline: Optional[TimelinePanel] = None
    monitor: Optional[MonitorPanel] = None
    advisor: Optional[AdvisorPanel] = None
    execution: Optional[ExecutionPanel] = None
    available_panels: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
