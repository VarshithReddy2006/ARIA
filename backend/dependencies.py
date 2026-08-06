"""Shared dependency singletons for the Repo Intelligence Agent API.

All service objects are constructed lazily or during FastAPI app lifespan and
provided across routers via Depends() or getter functions.

The ``ANALYSIS_STORE`` dict and its persistence helpers also live here so that
the main ``api.py`` and every router can import from a single authoritative
location without circular dependencies.
"""

import asyncio
import json
import logging
import os
import sys
import threading
from typing import Any, Dict, Optional, Type

from fastapi import Request
from ria.container import Container, build_container

from backend.settings import settings
from storage import JsonSnapshotStore

from core import AnalysisCache, AnalysisRegistry, BuildPipeline

from models.schemas import (
    ArchitectureSummary,
    ComponentRelationship,
    RepositoryAnalysis,
)
from memory.chroma_store import ChromaStore
from services.github_service import GitHubService
from services.chunking_service import CodeChunker
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService
from services.architecture_service import ArchitectureService
from services.graph_service import GraphService
from services.reading_order_service import ReadingOrderService
from services.impact_analysis_service import ImpactAnalysisService
from services.arch_context_service import ArchContextService
from services.graph_serializer import GraphSerializer
from services.symbol_service import SymbolService
from services.pr_intelligence_service import PRIntelligenceService
from services.architecture_drift_service import ArchitectureDriftService
from services.dead_code_service import DeadCodeService
from services.git_history_service import GitHistoryService
from services.call_graph_service import CallGraphService
from services.api_surface_service import APISurfaceService
from services.breaking_change_analyzer import BreakingChangeAnalyzer
from services.report.composer import ReportComposer
from services.report.renderer import HTMLRenderer, MarkdownRenderer, PDFRenderer
from services.twin_builder import RepositoryTwinBuilder
from services.twin_navigator import RepositoryTwinNavigator
from services.knowledge_graph_builder import RepositoryKnowledgeGraphBuilder
from services.knowledge_graph_navigator import RepositoryKnowledgeGraphNavigator
from services.retrieval_engine import StructuralRetrievalEngine
from services.reasoning_engine import EngineeringReasoningEngine
from services.graph_rag import ChatPipeline, GraphRAGService
from services.memory_service import EngineeringMemoryService
from services.repository_inspector import RepositoryInspector
from services.continuous_monitoring import ContinuousMonitoringService, ImmediatePolicy
from services.advisor import AdvisorService
from services.execution_planner import ExecutionPlannerService
from services.workspace import WorkspaceCoordinator, WorkspaceService


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Analysis store — persisted to disk so data survives server restarts
# ---------------------------------------------------------------------------
ANALYSIS_STORE: Dict[str, Dict[str, Any]] = {}
_ANALYSIS_STORE_PATH = os.path.join("data", "analysis_store.json")
_persist_lock = asyncio.Lock()


def _load_analysis_store() -> None:
    """Load persisted analysis data from disk into ANALYSIS_STORE on startup."""
    global ANALYSIS_STORE
    if not os.path.exists(_ANALYSIS_STORE_PATH):
        return
    try:
        with open(_ANALYSIS_STORE_PATH, "r", encoding="utf-8") as fh:
            raw: Dict[str, Any] = json.load(fh)
    except Exception as exc:
        logger.warning("Could not read analysis store from disk: %s", exc)
        return

    loaded = 0
    for repo_name, entry in raw.items():
        try:
            analysis_data = RepositoryAnalysis.model_validate(entry["analysis"])
            arch_raw = entry["architecture"]
            relationships = [
                ComponentRelationship(**r) for r in arch_raw.get("relationships", [])
            ]
            architecture_data = ArchitectureSummary(
                summary=arch_raw.get("summary", ""),
                reading_order=arch_raw.get("reading_order", []),
                relationships=relationships,
            )
            ANALYSIS_STORE[repo_name] = {
                "analysis": analysis_data,
                "architecture": architecture_data,
            }
            loaded += 1
        except Exception as exc:
            logger.warning(
                "Skipping malformed analysis store entry for '%s': %s", repo_name, exc
            )

    if loaded:
        logger.info(
            "Loaded %d repository entries from analysis store (%s).",
            loaded,
            _ANALYSIS_STORE_PATH,
        )


def _serialise_store() -> Dict[str, Any]:
    """Serialise ANALYSIS_STORE to a plain JSON-safe dict."""
    out: Dict[str, Any] = {}
    for repo_name, entry in ANALYSIS_STORE.items():
        try:
            analysis_obj = entry["analysis"]
            arch_obj = entry["architecture"]
            out[repo_name] = {
                "analysis": (
                    analysis_obj.model_dump()
                    if hasattr(analysis_obj, "model_dump")
                    else analysis_obj
                ),
                "architecture": (
                    arch_obj.model_dump()
                    if hasattr(arch_obj, "model_dump")
                    else arch_obj
                ),
            }
        except Exception as exc:
            logger.warning(
                "Could not serialise store entry for '%s': %s", repo_name, exc
            )
    return out


async def _persist_analysis_store() -> None:
    """Write ANALYSIS_STORE to disk atomically (tmp file → rename)."""
    async with _persist_lock:
        try:
            payload = _serialise_store()
            await asyncio.to_thread(_write_store_atomic, payload)
            logger.debug("Analysis store persisted (%d entries).", len(payload))
        except Exception as exc:
            logger.error("Failed to persist analysis store: %s", exc, exc_info=True)


def _write_store_atomic(payload: Dict[str, Any]) -> None:
    """Write payload to _ANALYSIS_STORE_PATH via a tmp file + rename (atomic)."""
    os.makedirs(os.path.dirname(_ANALYSIS_STORE_PATH), exist_ok=True)
    tmp_path = _ANALYSIS_STORE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp_path, _ANALYSIS_STORE_PATH)


# ---------------------------------------------------------------------------
# Lazy Singleton Storage & Lock
# ---------------------------------------------------------------------------
_SINGLETONS: Dict[str, Any] = {}
# Service factories may resolve other lazy services while construction is in
# progress, so the same thread must be allowed to re-enter the creation lock.
_SINGLETON_LOCK = threading.RLock()


def _get_or_create(name: str, factory_fn) -> Any:
    mod = sys.modules.get(__name__)
    if mod and name in mod.__dict__:
        return mod.__dict__[name]

    if name in _SINGLETONS:
        return _SINGLETONS[name]

    with _SINGLETON_LOCK:
        if mod and name in mod.__dict__:
            return mod.__dict__[name]
        if name not in _SINGLETONS:
            _SINGLETONS[name] = factory_fn()
        return _SINGLETONS[name]


# ---------------------------------------------------------------------------
# RIA Composition Root Container Integration
# ---------------------------------------------------------------------------
_GLOBAL_CONTAINER: Optional[Container] = None
_CONTAINER_LOCK = threading.Lock()


def get_container(request: Request = None) -> Container:
    """FastAPI dependency to retrieve the application Container from request.app.state."""
    if (
        request is not None
        and hasattr(request, "app")
        and hasattr(request.app.state, "container")
    ):
        return request.app.state.container

    global _GLOBAL_CONTAINER
    if _GLOBAL_CONTAINER is None:
        with _CONTAINER_LOCK:
            if _GLOBAL_CONTAINER is None:
                _GLOBAL_CONTAINER = build_container(run_migrations=False)
    return _GLOBAL_CONTAINER


def get_git_client(request: Request = None):
    container = get_container(request)
    return container.git


def get_parser_service(request: Request = None):
    container = get_container(request)
    return container.parser_service


def get_repository_manager(request: Request = None):
    container = get_container(request)
    return container.repository_manager


def get_ingestion_service(request: Request = None):
    container = get_container(request)
    return container.ingestion_service


def get_commit_resolver(request: Request = None):
    container = get_container(request)
    return container.commit_resolver


# ---------------------------------------------------------------------------
# Dependency Getters / Factories
# ---------------------------------------------------------------------------
def get_snapshot_store() -> JsonSnapshotStore:
    return _get_or_create("snapshot_store", lambda: JsonSnapshotStore())


def get_analysis_cache() -> AnalysisCache:
    return _get_or_create(
        "analysis_cache", lambda: AnalysisCache(limit=settings.cache_size_limit)
    )


def get_analysis_registry() -> AnalysisRegistry:
    def _create_registry():
        reg = AnalysisRegistry()
        reg.register(
            "Symbol Index",
            SymbolService,
            dependencies=[],
            outputs=["symbols"],
            schema_version=SymbolService.get_schema_version(),
        )
        reg.register(
            "Dependency Graph",
            ArchitectureService,
            dependencies=["Symbol Index"],
            outputs=["graphs/dependency"],
            schema_version=ArchitectureService.get_schema_version(),
        )
        reg.register(
            "Call Graph",
            CallGraphService,
            dependencies=["Symbol Index", "Dependency Graph"],
            outputs=["graphs/call", "call_graphs"],
            schema_version=CallGraphService.get_schema_version(),
        )
        reg.register(
            "Git History",
            GitHistoryService,
            dependencies=["Dependency Graph"],
            outputs=["churn"],
            schema_version=GitHistoryService.get_schema_version(),
        )
        reg.register(
            "API Surface",
            APISurfaceService,
            dependencies=["Symbol Index", "Dependency Graph"],
            outputs=["api_surface"],
            schema_version=APISurfaceService.get_schema_version(),
        )
        return reg

    return _get_or_create("analysis_registry", _create_registry)


def get_build_pipeline() -> BuildPipeline:
    return _get_or_create(
        "build_pipeline",
        lambda: BuildPipeline(
            get_analysis_registry(), snapshot_store=get_snapshot_store()
        ),
    )


def get_github_service() -> GitHubService:
    return _get_or_create("github_service", lambda: GitHubService())


def get_embedding_service() -> EmbeddingService:
    return _get_or_create(
        "embedding_service",
        lambda: EmbeddingService(model_name=settings.embedding_model),
    )


def get_chroma_store() -> ChromaStore:
    return _get_or_create(
        "chroma_store",
        lambda: ChromaStore(persist_directory=settings.chroma_db_path),
    )


def get_chunker() -> CodeChunker:
    return _get_or_create("chunker", lambda: CodeChunker())


def get_retrieval_service() -> RetrievalService:
    return _get_or_create(
        "retrieval_service",
        lambda: RetrievalService(
            embedding_service=get_embedding_service(),
            chroma_store=get_chroma_store(),
        ),
    )


def get_architecture_service() -> ArchitectureService:
    return _get_or_create("architecture_service", lambda: ArchitectureService())


def get_graph_service() -> GraphService:
    return _get_or_create("graph_service", lambda: GraphService())


def get_graph_serializer() -> GraphSerializer:
    return _get_or_create(
        "graph_serializer",
        lambda: GraphSerializer(
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_reading_order_service() -> ReadingOrderService:
    return _get_or_create(
        "reading_order_service",
        lambda: ReadingOrderService(architecture_service=get_architecture_service()),
    )


def get_impact_analysis_service() -> ImpactAnalysisService:
    return _get_or_create(
        "impact_analysis_service",
        lambda: ImpactAnalysisService(architecture_service=get_architecture_service()),
    )


def get_arch_context_service() -> ArchContextService:
    return _get_or_create(
        "arch_context_service",
        lambda: ArchContextService(architecture_service=get_architecture_service()),
    )


def get_symbol_service() -> SymbolService:
    return _get_or_create("symbol_service", lambda: SymbolService())


def get_pr_intelligence_service() -> PRIntelligenceService:
    return _get_or_create(
        "pr_intelligence_service",
        lambda: PRIntelligenceService(
            github_service=get_github_service(),
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_architecture_drift_service() -> ArchitectureDriftService:
    return _get_or_create(
        "architecture_drift_service",
        lambda: ArchitectureDriftService(
            github_service=get_github_service(),
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
            pr_intelligence_service=get_pr_intelligence_service(),
        ),
    )


def get_dead_code_service() -> DeadCodeService:
    return _get_or_create(
        "dead_code_service",
        lambda: DeadCodeService(
            github_service=get_github_service(),
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_git_history_service() -> GitHistoryService:
    return _get_or_create(
        "git_history_service",
        lambda: GitHistoryService(
            github_service=get_github_service(),
            graph_service=get_graph_service(),
        ),
    )


def get_call_graph_service() -> CallGraphService:
    return _get_or_create(
        "call_graph_service",
        lambda: CallGraphService(
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
        ),
    )


def get_api_surface_service() -> APISurfaceService:
    return _get_or_create(
        "api_surface_service",
        lambda: APISurfaceService(
            symbol_service=get_symbol_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_breaking_change_analyzer() -> Type[BreakingChangeAnalyzer]:
    return BreakingChangeAnalyzer


def get_report_composer() -> ReportComposer:
    return _get_or_create(
        "report_composer",
        lambda: ReportComposer(
            store=ANALYSIS_STORE,
            symbol_service=get_symbol_service(),
            call_graph_service=get_call_graph_service(),
            dead_code_service=get_dead_code_service(),
            git_history_service=get_git_history_service(),
            graph_service=get_graph_service(),
        ),
    )


def get_html_renderer() -> HTMLRenderer:
    return _get_or_create("html_renderer", lambda: HTMLRenderer())


def get_markdown_renderer() -> MarkdownRenderer:
    return _get_or_create("markdown_renderer", lambda: MarkdownRenderer())


def get_pdf_renderer() -> PDFRenderer:
    return _get_or_create("pdf_renderer", lambda: PDFRenderer())


def get_repository_twin_builder() -> RepositoryTwinBuilder:
    return _get_or_create(
        "repository_twin_builder",
        lambda: RepositoryTwinBuilder(
            store=ANALYSIS_STORE,
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
            report_composer=get_report_composer(),
            dead_code_service=get_dead_code_service(),
            github_service=get_github_service(),
            snapshot_store=get_snapshot_store(),
        ),
    )


def get_repository_twin_navigator() -> RepositoryTwinNavigator:
    return _get_or_create(
        "repository_twin_navigator", lambda: RepositoryTwinNavigator()
    )


def get_repository_knowledge_graph_builder() -> RepositoryKnowledgeGraphBuilder:
    return _get_or_create(
        "repository_knowledge_graph_builder",
        lambda: RepositoryKnowledgeGraphBuilder(
            twin_builder=get_repository_twin_builder(),
            cache=get_analysis_cache(),
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
        ),
    )


def get_repository_knowledge_graph_navigator() -> RepositoryKnowledgeGraphNavigator:
    return _get_or_create(
        "repository_knowledge_graph_navigator",
        lambda: RepositoryKnowledgeGraphNavigator(
            builder=get_repository_knowledge_graph_builder()
        ),
    )


def get_structural_retrieval_engine() -> StructuralRetrievalEngine:
    return _get_or_create(
        "structural_retrieval_engine",
        lambda: StructuralRetrievalEngine(
            navigator=get_repository_knowledge_graph_navigator(),
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
            retrieval_service=get_retrieval_service(),
        ),
    )


def get_engineering_reasoning_engine() -> EngineeringReasoningEngine:
    return _get_or_create(
        "engineering_reasoning_engine",
        lambda: EngineeringReasoningEngine(),
    )


def get_graph_rag_service() -> GraphRAGService:
    return _get_or_create(
        "graph_rag_service",
        lambda: GraphRAGService(
            pipeline=ChatPipeline(
                retrieval_engine=get_structural_retrieval_engine(),
                reasoning_engine=get_engineering_reasoning_engine(),
            )
        ),
    )


def get_engineering_memory_service() -> EngineeringMemoryService:
    return _get_or_create(
        "engineering_memory_service",
        lambda: EngineeringMemoryService(),
    )


def get_repository_inspector() -> RepositoryInspector:
    return _get_or_create(
        "repository_inspector",
        lambda: RepositoryInspector(),
    )


def get_continuous_monitoring_service() -> ContinuousMonitoringService:
    return _get_or_create(
        "continuous_monitoring_service",
        lambda: ContinuousMonitoringService(
            repository_inspector=get_repository_inspector(),
            default_policy=ImmediatePolicy(),
        ),
    )


def get_advisor_service() -> AdvisorService:
    return _get_or_create("advisor_service", lambda: AdvisorService())


def get_execution_planner_service() -> ExecutionPlannerService:
    return _get_or_create(
        "execution_planner_service",
        lambda: ExecutionPlannerService(),
    )


def get_workspace_service() -> WorkspaceService:
    def _create_ws():
        coord = WorkspaceCoordinator(
            twin_builder=get_repository_twin_builder(),
            knowledge_graph_builder=get_repository_knowledge_graph_builder(),
            repository_inspector=get_repository_inspector(),
            engineering_memory_service=get_engineering_memory_service(),
            continuous_monitoring_service=get_continuous_monitoring_service(),
            advisor_service=get_advisor_service(),
            execution_planner_service=get_execution_planner_service(),
        )
        return WorkspaceService(coord)

    return _get_or_create("workspace_service", _create_ws)


def get_retrieval_pipeline():
    def _create_pipeline():
        from services.chat.retrieval_pipeline import RetrievalPipeline
        from services.chat.intent_router import IntentRouter

        router = IntentRouter(
            architecture_service=get_architecture_service(),
            graph_service=get_graph_service(),
            symbol_service=get_symbol_service(),
            reading_order_service=get_reading_order_service(),
            impact_analysis_service=get_impact_analysis_service(),
            api_surface_service=get_api_surface_service(),
            call_graph_service=get_call_graph_service(),
        )

        return RetrievalPipeline(
            embedding_service=get_embedding_service(),
            chroma_store=get_chroma_store(),
            arch_context_service=get_arch_context_service(),
            intent_router=router,
        )

    return _get_or_create("retrieval_pipeline", _create_pipeline)


def get_service_by_class(cls: Type[Any]) -> Optional[Any]:
    if cls == SymbolService:
        return get_symbol_service()
    if cls == ArchitectureService:
        return get_architecture_service()
    if cls == CallGraphService:
        return get_call_graph_service()
    if cls == GitHistoryService:
        return get_git_history_service()
    if cls == APISurfaceService:
        return get_api_surface_service()
    return None


_GETTERS = {
    "container": get_container,
    "git_client": get_git_client,
    "parser_service": get_parser_service,
    "repository_manager": get_repository_manager,
    "ingestion_service": get_ingestion_service,
    "commit_resolver": get_commit_resolver,
    "snapshot_store": get_snapshot_store,
    "analysis_cache": get_analysis_cache,
    "analysis_registry": get_analysis_registry,
    "build_pipeline": get_build_pipeline,
    "github_service": get_github_service,
    "embedding_service": get_embedding_service,
    "chroma_store": get_chroma_store,
    "chunker": get_chunker,
    "retrieval_service": get_retrieval_service,
    "architecture_service": get_architecture_service,
    "graph_service": get_graph_service,
    "graph_serializer": get_graph_serializer,
    "reading_order_service": get_reading_order_service,
    "impact_analysis_service": get_impact_analysis_service,
    "arch_context_service": get_arch_context_service,
    "symbol_service": get_symbol_service,
    "pr_intelligence_service": get_pr_intelligence_service,
    "architecture_drift_service": get_architecture_drift_service,
    "dead_code_service": get_dead_code_service,
    "git_history_service": get_git_history_service,
    "call_graph_service": get_call_graph_service,
    "api_surface_service": get_api_surface_service,
    "breaking_change_analyzer": get_breaking_change_analyzer,
    "report_composer": get_report_composer,
    "html_renderer": get_html_renderer,
    "markdown_renderer": get_markdown_renderer,
    "pdf_renderer": get_pdf_renderer,
    "repository_twin_builder": get_repository_twin_builder,
    "repository_twin_navigator": get_repository_twin_navigator,
    "repository_knowledge_graph_builder": get_repository_knowledge_graph_builder,
    "repository_knowledge_graph_navigator": get_repository_knowledge_graph_navigator,
    "structural_retrieval_engine": get_structural_retrieval_engine,
    "engineering_reasoning_engine": get_engineering_reasoning_engine,
    "graph_rag_service": get_graph_rag_service,
    "engineering_memory_service": get_engineering_memory_service,
    "repository_inspector": get_repository_inspector,
    "continuous_monitoring_service": get_continuous_monitoring_service,
    "advisor_service": get_advisor_service,
    "execution_planner_service": get_execution_planner_service,
    "workspace_service": get_workspace_service,
    "retrieval_pipeline": get_retrieval_pipeline,
}


def __getattr__(name: str) -> Any:
    if name in _GETTERS:
        return _GETTERS[name]()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
