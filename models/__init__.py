"""Shared schemas and models package for ARIA."""

from .schemas import (
    RepositoryAnalysis,
    ArchitectureSummary,
    ComponentRelationship,
    ImplementationPlan,
    ImplementationPlanStep,
    EvaluationResult,
    IssueMapResponse,
)
from .architecture import (
    ParsedFile,
    GraphNode,
    GraphEdge,
    ArchitectureSummary as ArchitectureIntelSummary,
)
from .phase2 import (
    ReadingOrderEntry,
    ReadingOrder,
    DependencyPath,
    ImpactAnalysis,
    ArchContext,
)
from .pr_intelligence import (
    PRAnalyzeRequest,
    ChangedFile,
    SymbolChange,
    PropagationPath,
    RiskBreakdown,
    ReviewFocusArea,
    PRAnalysisResult,
)
from .architecture_drift import (
    PRDriftRequest,
    DependencyEdge,
    CouplingChange,
    PRDriftResult,
)
from .dead_code import (
    DeadFile,
    OrphanModule,
    DeadDependencyChain,
    DeadCodeRequest,
    DeadCodeResult,
)
from .call_graph import (
    CallNode,
    CallEdge,
    BlastRadiusResult,
    CallHierarchyNode,
    CallGraphSummary,
)
from .api_surface import (
    Visibility,
    ApiKind,
    ApiStatus,
    BreakingChangeKind,
    ClassifiedSymbol,
    BreakingChange,
    APISurfaceStats,
    APISurface,
)
from .report import (
    ScoreBreakdown,
    ReportMetadata,
    ArchReportSection,
    ApiReportSection,
    HygieneReportSection,
    OnboardingReportSection,
    ReportDataModel,
)

from .build_manifest import BuildManifest

from .build_event import (
    BuildEvent,
    TaskQueued,
    TaskStarted,
    TaskCompleted,
    TaskSkipped,
    TaskFailed,
    StageCompleted,
    BuildCompleted,
)

__all__ = [
    # Existing schemas
    "RepositoryAnalysis",
    "ArchitectureSummary",
    "ComponentRelationship",
    "ImplementationPlan",
    "ImplementationPlanStep",
    "EvaluationResult",
    "IssueMapResponse",
    # Build Manifest
    "BuildManifest",
    # Build Events
    "BuildEvent",
    "TaskQueued",
    "TaskStarted",
    "TaskCompleted",
    "TaskSkipped",
    "TaskFailed",
    "StageCompleted",
    "BuildCompleted",
    # Phase 1 — Architecture Foundation
    "ParsedFile",
    "GraphNode",
    "GraphEdge",
    "ArchitectureIntelSummary",
    # Phase 2 — Repository Intelligence
    "ReadingOrderEntry",
    "ReadingOrder",
    "DependencyPath",
    "ImpactAnalysis",
    "ArchContext",
    # PR Intelligence
    "PRAnalyzeRequest",
    "ChangedFile",
    "SymbolChange",
    "PropagationPath",
    "RiskBreakdown",
    "ReviewFocusArea",
    "PRAnalysisResult",
    # Architecture Drift
    "PRDriftRequest",
    "DependencyEdge",
    "CouplingChange",
    "PRDriftResult",
    # Dead Code Intelligence
    "DeadFile",
    "OrphanModule",
    "DeadDependencyChain",
    "DeadCodeRequest",
    "DeadCodeResult",
    # Call Graph Intelligence
    "CallNode",
    "CallEdge",
    "BlastRadiusResult",
    "CallHierarchyNode",
    "CallGraphSummary",
    # API Surface Intelligence
    "Visibility",
    "ApiKind",
    "ApiStatus",
    "BreakingChangeKind",
    "ClassifiedSymbol",
    "BreakingChange",
    "APISurfaceStats",
    "APISurface",
    "ScoreBreakdown",
    "ReportMetadata",
    "ArchReportSection",
    "ApiReportSection",
    "HygieneReportSection",
    "OnboardingReportSection",
    "ReportDataModel",
]
