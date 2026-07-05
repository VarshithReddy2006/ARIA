"""Shared dependency singletons for the Repo Intelligence Agent API.

All service objects are constructed **once** at process startup and shared
across every router via direct import.  FastAPI's ``Depends()`` mechanism is
not used here because the services are stateless and thread-safe — constructing
them once is both correct and significantly cheaper than re-instantiating on
every request.

The ``ANALYSIS_STORE`` dict and its persistence helpers also live here so that
the main ``api.py`` and every router can import from a single authoritative
location without circular dependencies.

Import pattern inside routers
------------------------------
    from backend.dependencies import (
        ANALYSIS_STORE,
        github_service,
        embedding_service,
        ...
        _persist_analysis_store,
    )
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Type, Optional

from backend.settings import settings
from storage import JsonSnapshotStore

from core import AnalysisCache, AnalysisRegistry, BuildPipeline

from models.schemas import (
    ArchitectureSummary,
    ComponentRelationship,
    RepositoryAnalysis,
)
from memory.chroma_store import ChromaStore
from services.github_service import GitHubConfig, GitHubService
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
from services.graph_rag import GraphRAGService
from services.memory_service import EngineeringMemoryService
from services.repository_inspector import RepositoryInspector
from services.continuous_monitoring import ContinuousMonitoringService, ImmediatePolicy
from services.advisor import AdvisorService
from services.execution_planner import ExecutionPlannerService
from services.workspace import WorkspaceCoordinator, WorkspaceService


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup diagnostics — token presence only (no prefix logged for security)
# ---------------------------------------------------------------------------
_token = GitHubConfig.load_token()
logger.info("GitHub token loaded: %s", bool(_token))

# ---------------------------------------------------------------------------
# Analysis store — persisted to disk so data survives server restarts
# ---------------------------------------------------------------------------
ANALYSIS_STORE: Dict[str, Dict[str, Any]] = {}
_ANALYSIS_STORE_PATH = os.path.join("data", "analysis_store.json")
_persist_lock = asyncio.Lock()


def _load_analysis_store() -> None:
    """Load persisted analysis data from disk into ANALYSIS_STORE on startup.

    Reconstructs Pydantic models from the stored JSON dicts.  Any entry that
    fails to deserialise is skipped (logged at WARNING) so a single corrupt
    record never blocks the entire store from loading.
    """
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
    """Write ANALYSIS_STORE to disk atomically (tmp file → rename).

    Uses an asyncio Lock to prevent concurrent writes from corrupting the file.
    Runs the blocking I/O in a thread so the event loop is not blocked.
    """
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
# Core service singletons — constructed once per process
# ---------------------------------------------------------------------------
CHROMA_DB_PATH = settings.chroma_db_path

# Core Architecture singletons
snapshot_store = JsonSnapshotStore()
analysis_cache = AnalysisCache(limit=settings.cache_size_limit)
analysis_registry = AnalysisRegistry()
build_pipeline = BuildPipeline(analysis_registry)

# Register builders to DAG
analysis_registry.register(
    "Symbol Index",
    SymbolService,
    dependencies=[],
    outputs=["symbols"],
    schema_version=SymbolService.get_schema_version(),
)
analysis_registry.register(
    "Dependency Graph",
    ArchitectureService,
    dependencies=["Symbol Index"],
    outputs=["graphs/dependency"],
    schema_version=ArchitectureService.get_schema_version(),
)
analysis_registry.register(
    "Call Graph",
    CallGraphService,
    dependencies=["Symbol Index", "Dependency Graph"],
    outputs=["graphs/call", "call_graphs"],
    schema_version=CallGraphService.get_schema_version(),
)
analysis_registry.register(
    "Git History",
    GitHistoryService,
    dependencies=["Dependency Graph"],
    outputs=["churn"],
    schema_version=GitHistoryService.get_schema_version(),
)
analysis_registry.register(
    "API Surface",
    APISurfaceService,
    dependencies=["Symbol Index", "Dependency Graph"],
    outputs=["api_surface"],
    schema_version=APISurfaceService.get_schema_version(),
)
analysis_registry.register(
    "Module Stability", type(None), dependencies=["API Surface"], outputs=["stability"]
)
analysis_registry.register(
    "Dependency Smells",
    type(None),
    dependencies=["Dependency Graph"],
    outputs=["dependency_smells"],
)
analysis_registry.register(
    "Architecture Health",
    type(None),
    dependencies=["Dependency Graph", "Call Graph"],
    outputs=["health"],
)

github_service = GitHubService()
embedding_service = EmbeddingService(model_name=settings.embedding_model)
chroma_store = ChromaStore(persist_directory=CHROMA_DB_PATH)
chunker = CodeChunker()
retrieval_service = RetrievalService(
    embedding_service=embedding_service,
    chroma_store=chroma_store,
)
architecture_service = ArchitectureService()
graph_service = GraphService()
graph_serializer = GraphSerializer(
    graph_service=graph_service,
    architecture_service=architecture_service,
)
reading_order_service = ReadingOrderService(architecture_service=architecture_service)
impact_analysis_service = ImpactAnalysisService(
    architecture_service=architecture_service
)
arch_context_service = ArchContextService(architecture_service=architecture_service)
symbol_service = SymbolService()
pr_intelligence_service = PRIntelligenceService(
    github_service=github_service,
    symbol_service=symbol_service,
    graph_service=graph_service,
    architecture_service=architecture_service,
)
architecture_drift_service = ArchitectureDriftService(
    github_service=github_service,
    symbol_service=symbol_service,
    graph_service=graph_service,
    architecture_service=architecture_service,
    pr_intelligence_service=pr_intelligence_service,
)
dead_code_service = DeadCodeService(
    github_service=github_service,
    graph_service=graph_service,
    architecture_service=architecture_service,
)
git_history_service = GitHistoryService(
    github_service=github_service,
    graph_service=graph_service,
)
call_graph_service = CallGraphService(
    symbol_service=symbol_service,
    graph_service=graph_service,
)
api_surface_service = APISurfaceService(
    symbol_service=symbol_service,
    architecture_service=architecture_service,
)
breaking_change_analyzer = BreakingChangeAnalyzer

report_composer = ReportComposer()
html_renderer = HTMLRenderer()
markdown_renderer = MarkdownRenderer()
pdf_renderer = PDFRenderer()

repository_twin_builder = RepositoryTwinBuilder()
repository_twin_navigator = RepositoryTwinNavigator()

repository_knowledge_graph_builder = RepositoryKnowledgeGraphBuilder()
repository_knowledge_graph_navigator = RepositoryKnowledgeGraphNavigator()

structural_retrieval_engine = StructuralRetrievalEngine()
engineering_reasoning_engine = EngineeringReasoningEngine()

graph_rag_service = GraphRAGService()

engineering_memory_service = EngineeringMemoryService()

repository_inspector = RepositoryInspector()

continuous_monitoring_service = ContinuousMonitoringService(
    repository_inspector=repository_inspector,
    default_policy=ImmediatePolicy(),
)

advisor_service = AdvisorService()

execution_planner_service = ExecutionPlannerService()

workspace_service = WorkspaceService(
    WorkspaceCoordinator(
        twin_builder=repository_twin_builder,
        knowledge_graph_builder=repository_knowledge_graph_builder,
        repository_inspector=repository_inspector,
        engineering_memory_service=engineering_memory_service,
        continuous_monitoring_service=continuous_monitoring_service,
        advisor_service=advisor_service,
        execution_planner_service=execution_planner_service,
    )
)

# ---------------------------------------------------------------------------
# Repository Chat v2 — RetrievalPipeline singleton
# ---------------------------------------------------------------------------
# Constructed lazily to avoid circular imports at module load time.
# Callers import `get_retrieval_pipeline()` rather than a bare singleton so
# the IntentRouter can be wired up with fully initialised services.
_retrieval_pipeline = None


def get_retrieval_pipeline():
    """Return the singleton RetrievalPipeline, constructing it on first call."""
    global _retrieval_pipeline
    if _retrieval_pipeline is not None:
        return _retrieval_pipeline

    from services.chat.retrieval_pipeline import RetrievalPipeline
    from services.chat.intent_router import IntentRouter

    router = IntentRouter(
        architecture_service=architecture_service,
        graph_service=graph_service,
        symbol_service=symbol_service,
        reading_order_service=reading_order_service,
        impact_analysis_service=impact_analysis_service,
        api_surface_service=api_surface_service,
        call_graph_service=call_graph_service,
    )

    _retrieval_pipeline = RetrievalPipeline(
        embedding_service=embedding_service,
        chroma_store=chroma_store,
        arch_context_service=arch_context_service,
        intent_router=router,
    )
    return _retrieval_pipeline


def get_service_by_class(cls: Type[Any]) -> Optional[Any]:

    if cls == SymbolService:
        return symbol_service
    if cls == ArchitectureService:
        return architecture_service
    if cls == CallGraphService:
        return call_graph_service
    if cls == GitHistoryService:
        return git_history_service
    if cls == APISurfaceService:
        return api_surface_service
    return None
