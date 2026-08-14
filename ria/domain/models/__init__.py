"""Domain models package.

Re-exports domain models for ARIA.
"""

from __future__ import annotations

from ria.domain.models.analysis_models import (
    AnalysisResult,
    ArchitectureAnalysis,
    CrossReference,
    DependencyAnalysis,
    ImpactAnalysis,
    PatternMatch,
)
from ria.domain.models.context_evidence import (
    ContextBundle,
    ContextCandidate,
    ContextEvidence,
)
from ria.domain.models.context_id import ContextId
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_request import (
    ContextRequest,
    ConversationContext,
    IntentClassification,
    RepositoryContext,
)
from ria.domain.models.context_result import (
    CompressionResult,
    ContextCacheKey,
    ContextFingerprint,
    ContextMetadata,
    ContextStatistics,
    RankingResult,
    RetrievalResult,
)
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptMessage,
    PromptSection,
)
from ria.domain.models.query_id import QueryId
from ria.domain.models.query_identity import QueryCacheKey, QueryFingerprint
from ria.domain.models.query_request import (
    QueryContext,
    QueryFilter,
    QueryProjection,
    QueryRequest,
)
from ria.domain.models.query_result import (
    QueryMatch,
    QueryMetadata,
    QueryStatistics,
    QueryResult,
)
from ria.domain.models.reasoning_id import ReasoningId
from ria.domain.models.reasoning_model import (
    ModelRequest,
    ModelResponse,
    PromptExecution,
    PromptTemplate,
    ProviderConfiguration,
    StreamingChunk,
    StreamingSession,
)
from ria.domain.models.reasoning_pipeline import ReasoningPlan, ReasoningStep
from ria.domain.models.reasoning_request import ReasoningContext, ReasoningRequest
from ria.domain.models.reasoning_result import (
    ReasoningCacheKey,
    ReasoningCitation,
    ReasoningEvidence,
    ReasoningFingerprint,
    ReasoningMetadata,
    ReasoningResult,
    ReasoningStatistics,
    ResponseQuality,
    ValidationResult,
)
from ria.domain.models.repository_metrics import RepositoryMetrics
from ria.domain.models.repository_state import RepositoryState
from ria.domain.models.repository_twin import RepositoryTwin
from ria.domain.models.consistency_report import ConsistencyReport
from ria.domain.models.synchronization_result import SynchronizationResult
from ria.domain.models.token_budget import TokenBudget
from ria.domain.models.twin_id import TwinId
from ria.domain.models.twin_identity import TwinCacheKey, TwinFingerprint, TwinVersion
from ria.domain.models.twin_result import TwinDiagnostic, TwinMetadata, TwinStatistics
from ria.domain.models.twin_snapshot import TwinSnapshot

from ria.domain.models.agent_id import AgentId
from ria.domain.models.task_id import TaskId
from ria.domain.models.agent_definition import (
    AgentRole,
    AgentCapability,
    AgentState,
    AgentDefinition,
)
from ria.domain.models.agent_task import (
    TaskDependency,
    TaskPlan,
    AgentTask,
    TaskAssignment,
    TaskExecution,
    TaskFailure,
    TaskResult,
)
from ria.domain.models.agent_execution import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionSession,
    SharedContext,
)
from ria.domain.models.agent_communication import AgentMessage, AgentConversation
from ria.domain.models.agent_result import (
    AgentMetadata,
    AgentStatistics,
    AgentFingerprint,
    AgentCacheKey,
    ExecutionReport,
)

from ria.domain.models.workflow_id import WorkflowId
from ria.domain.models.workflow_definition import (
    WorkflowState,
    WorkflowAction,
    WorkflowTransition,
    WorkflowStep,
    WorkflowDefinition,
)
from ria.domain.models.workflow_execution import (
    WorkflowContext,
    WorkflowExecution,
    WorkflowFailure,
    WorkflowResult,
)
from ria.domain.models.workflow_approval import (
    ApprovalDecision,
    ApprovalRequest,
    WorkflowApproval,
)
from ria.domain.models.workflow_rollback import (
    ExecutionCheckpoint,
    ExecutionSnapshot,
    RollbackAction,
    RollbackPlan,
)
from ria.domain.models.workflow_audit import AuditEntry, AuditTrail
from ria.domain.models.workflow_verification import VerificationResult
from ria.domain.models.workflow_result import (
    WorkflowMetadata,
    WorkflowStatistics,
    WorkflowFingerprint,
    WorkflowCacheKey,
)

from ria.domain.models.execution_id import ExecutionId
from ria.domain.models.execution_definition import (
    ExecutionState,
    ExecutionAction,
    ExecutionDefinition,
)
from ria.domain.models.patch_models import (
    PatchChunk,
    PatchFile,
    PatchStatistics,
    PatchValidation,
    ExecutionPatch,
)
from ria.domain.models.repository_edit_models import (
    RepositoryEdit,
    RepositorySnapshot,
    RepositoryVersion,
    BranchDefinition,
)
from ria.domain.models.commit_pr_models import (
    CommitMessage,
    CommitPlan,
    MergeStrategy,
    PullRequestDraft,
)
from ria.domain.models.learning_analytics_models import (
    LearningRecord,
    ExecutionHistory,
    ExecutionAnalytics,
    ExecutionPolicy,
)
from ria.domain.models.execution_result_models import (
    ExecutionMetadata,
    ExecutionFingerprint,
    ExecutionCacheKey,
)

__all__ = [
    "AnalysisResult",
    "ArchitectureAnalysis",
    "CompressionResult",
    "ConsistencyReport",
    "ContextBundle",
    "ContextCandidate",
    "ContextCitation",
    "ContextEvidence",
    "ContextFingerprint",
    "ContextCacheKey",
    "ContextId",
    "ContextMetadata",
    "ContextPlan",
    "ContextRequest",
    "ContextStatistics",
    "ConversationContext",
    "CrossReference",
    "DependencyAnalysis",
    "ImpactAnalysis",
    "IntentClassification",
    "ModelRequest",
    "ModelResponse",
    "PatternMatch",
    "PromptContext",
    "PromptExecution",
    "PromptMessage",
    "PromptSection",
    "PromptTemplate",
    "ProviderConfiguration",
    "QueryCacheKey",
    "QueryContext",
    "QueryFilter",
    "QueryFingerprint",
    "QueryId",
    "QueryMatch",
    "QueryMetadata",
    "QueryProjection",
    "QueryRequest",
    "QueryResult",
    "QueryStatistics",
    "RankingResult",
    "ReasoningCacheKey",
    "ReasoningCitation",
    "ReasoningContext",
    "ReasoningEvidence",
    "ReasoningFingerprint",
    "ReasoningId",
    "ReasoningMetadata",
    "ReasoningPlan",
    "ReasoningRequest",
    "ReasoningResult",
    "ReasoningStatistics",
    "ReasoningStep",
    "RepositoryContext",
    "RepositoryMetrics",
    "RepositoryState",
    "RepositoryTwin",
    "ResponseQuality",
    "RetrievalResult",
    "StreamingChunk",
    "StreamingSession",
    "SynchronizationResult",
    "TokenBudget",
    "TwinCacheKey",
    "TwinDiagnostic",
    "TwinFingerprint",
    "TwinId",
    "TwinMetadata",
    "TwinSnapshot",
    "TwinStatistics",
    "TwinVersion",
    "ValidationResult",
    "AgentId",
    "TaskId",
    "AgentRole",
    "AgentCapability",
    "AgentState",
    "AgentDefinition",
    "TaskDependency",
    "TaskPlan",
    "AgentTask",
    "TaskAssignment",
    "TaskExecution",
    "TaskFailure",
    "TaskResult",
    "ExecutionContext",
    "ExecutionPlan",
    "ExecutionSession",
    "SharedContext",
    "AgentMessage",
    "AgentConversation",
    "AgentMetadata",
    "AgentStatistics",
    "AgentFingerprint",
    "AgentCacheKey",
    "ExecutionReport",
    "WorkflowId",
    "WorkflowState",
    "WorkflowAction",
    "WorkflowTransition",
    "WorkflowStep",
    "WorkflowDefinition",
    "WorkflowContext",
    "WorkflowExecution",
    "WorkflowFailure",
    "WorkflowResult",
    "ApprovalDecision",
    "ApprovalRequest",
    "WorkflowApproval",
    "ExecutionCheckpoint",
    "ExecutionSnapshot",
    "RollbackAction",
    "RollbackPlan",
    "AuditEntry",
    "AuditTrail",
    "VerificationResult",
    "WorkflowMetadata",
    "WorkflowStatistics",
    "WorkflowFingerprint",
    "WorkflowCacheKey",
    "ExecutionId",
    "ExecutionState",
    "ExecutionAction",
    "ExecutionDefinition",
    "PatchChunk",
    "PatchFile",
    "PatchStatistics",
    "PatchValidation",
    "ExecutionPatch",
    "RepositoryEdit",
    "RepositorySnapshot",
    "RepositoryVersion",
    "BranchDefinition",
    "CommitMessage",
    "CommitPlan",
    "MergeStrategy",
    "PullRequestDraft",
    "LearningRecord",
    "ExecutionHistory",
    "ExecutionAnalytics",
    "ExecutionPolicy",
    "ExecutionMetadata",
    "ExecutionFingerprint",
    "ExecutionCacheKey",
]
