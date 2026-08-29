"""Shared dependency singletons for the ARIA API.

All service objects are constructed lazily or during FastAPI app lifespan and
provided across routers via Depends() or getter functions.

The ``ANALYSIS_STORE`` dict and its persistence helpers also live here so that
the main ``api.py`` and every router can import from a single authoritative
location without circular dependencies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

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

if TYPE_CHECKING:
    from memory.chroma_store import ChromaStore
    from memory.qdrant_store import QdrantStore
    from memory.vector_store import VectorStore
    from services.advisor import AdvisorService
    from services.api_surface_service import APISurfaceService
    from services.arch_context_service import ArchContextService
    from services.architecture_drift_service import ArchitectureDriftService
    from services.architecture_service import ArchitectureService
    from services.breaking_change_analyzer import BreakingChangeAnalyzer
    from services.call_graph_service import CallGraphService
    from services.chunking_service import CodeChunker
    from services.continuous_monitoring import ContinuousMonitoringService
    from services.dead_code_service import DeadCodeService
    from services.embedding_service import EmbeddingService
    from services.reasoning_engine import EngineeringReasoningEngine
    from services.execution_planner import ExecutionPlannerService
    from services.git_history_service import GitHistoryService
    from services.github_service import GitHubService
    from services.graph_rag import GraphRAGService
    from services.graph_serializer import GraphSerializer
    from services.graph_service import GraphService
    from services.impact_analysis_service import ImpactAnalysisService
    from services.knowledge_graph_builder import RepositoryKnowledgeGraphBuilder
    from services.knowledge_graph_navigator import RepositoryKnowledgeGraphNavigator
    from services.memory_service import EngineeringMemoryService
    from services.pr_intelligence_service import PRIntelligenceService
    from services.reading_order_service import ReadingOrderService
    from services.report.composer import ReportComposer
    from services.report.renderer import HTMLRenderer, MarkdownRenderer, PDFRenderer
    from services.repository_inspector import RepositoryInspector
    from services.retrieval_engine import StructuralRetrievalEngine
    from services.retrieval_service import RetrievalService
    from services.symbol_service import SymbolService
    from services.twin_builder import RepositoryTwinBuilder
    from services.twin_navigator import RepositoryTwinNavigator
    from services.workspace import WorkspaceService


logger = logging.getLogger(__name__)


def _get_analysis_store_path() -> str:
    override = os.environ.get("ANALYSIS_STORE_PATH")
    if override:
        return override
    if os.path.exists("/app/data"):
        return "/app/data/analysis_store.json"
    return os.path.join("data", "analysis_store.json")


_ANALYSIS_STORE_PATH = _get_analysis_store_path()
_persist_lock = threading.Lock()


def normalize_repo_name(name_or_url: Any) -> str:
    """Normalize owner/repo or repository URL into standard lowercase 'owner/repo'."""
    if not name_or_url:
        return ""
    if isinstance(name_or_url, dict):
        if "metadata" in name_or_url and isinstance(name_or_url["metadata"], dict):
            meta_res = normalize_repo_name(name_or_url["metadata"])
            if meta_res:
                return meta_res
        full = name_or_url.get("full_name") or name_or_url.get("repo_name")
        if full:
            return normalize_repo_name(full)
        owner = name_or_url.get("owner")
        repo = name_or_url.get("name") or name_or_url.get("repo")
        if owner and repo:
            return f"{str(owner).strip().lower()}/{str(repo).strip().lower()}"
        return ""

    val = str(name_or_url).strip()
    if not val:
        return ""

    # Strip trailing slashes first
    val = val.rstrip("/")

    # Handle SSH URLs: git@github.com:owner/repo.git or ssh://git@github.com/owner/repo.git
    if "git@" in val and ":" in val:
        val = val.split(":", 1)[-1]

    # Handle protocol URLs: http:// or https://
    if "://" in val:
        val = val.split("://", 1)[-1]
        # Remove host domain e.g. github.com/...
        if "/" in val:
            val = val.split("/", 1)[-1]

    # Handle domain prefix without protocol: github.com/owner/repo or gitlab.com/owner/repo
    for domain in ("github.com/", "gitlab.com/", "bitbucket.org/"):
        if domain in val:
            val = val.split(domain, 1)[-1]

    val = val.strip("/")

    if val.endswith(".git"):
        val = val[:-4]

    val = val.strip("/")

    # Keep only owner/repo parts if formatted as path
    parts = [p for p in val.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0].lower()}/{parts[1].lower()}"
    elif len(parts) == 1:
        return parts[0].lower()

    return val.lower()


def _get_candidate_job_dirs() -> List[str]:
    """Return authoritative job state directories according to configuration."""
    jobs_dir_env = os.environ.get("JOB_STATE_DIR")
    if jobs_dir_env:
        return [jobs_dir_env]

    candidate_dirs = []
    try:
        from core.config import settings

        db_path = os.environ.get("SQLITE_DB_PATH") or getattr(
            settings, "sqlite_db_path", None
        )
        if db_path:
            base = os.path.dirname(os.path.abspath(db_path))
            candidate_dirs.append(os.path.join(base, "jobs"))
    except Exception:
        pass

    if os.path.exists("/app/data/jobs"):
        candidate_dirs.append("/app/data/jobs")
    candidate_dirs.append(os.path.join("data", "jobs"))

    seen = set()
    res = []
    for d in candidate_dirs:
        norm = os.path.abspath(d) if d else ""
        if norm and norm not in seen:
            seen.add(norm)
            res.append(d)
    return res


def recover_analysis_from_jobs(target_repo: str) -> Optional[Dict[str, Any]]:
    """Recover completed repository analysis from completed job files in JOB_STATE_DIR.
    
    Self-heals ANALYSIS_STORE and attempts to persist to analysis_store.json.
    """
    target_norm = normalize_repo_name(target_repo)
    if not target_norm:
        return None

    acceptable_statuses = {"completed", "success", "successful"}
    best_job: Optional[Dict[str, Any]] = None
    best_timestamp: float = -1.0
    best_job_id: str = ""
    best_analysis_raw = None
    best_arch_raw = None

    candidate_dirs = _get_candidate_job_dirs()
    for directory in candidate_dirs:
        if not directory or not os.path.isdir(directory):
            continue
        try:
            entries = os.listdir(directory)
        except Exception as exc:
            logger.warning("Could not list directory %s for job recovery: %s", directory, exc)
            continue

        for fname in entries:
            if not fname.endswith(".json"):
                continue
            job_file = os.path.join(directory, fname)
            try:
                with open(job_file, "r", encoding="utf-8") as fh:
                    job_data = json.load(fh)
            except Exception as exc:
                logger.debug("Failed to read job file %s: %s", job_file, exc)
                continue

            if not isinstance(job_data, dict):
                continue

            status = str(job_data.get("status", "")).strip().lower()
            if status not in acceptable_statuses:
                continue

            candidates = [
                job_data.get("repo_url"),
                job_data.get("repo"),
                job_data.get("repo_name"),
                job_data.get("url"),
            ]
            if isinstance(job_data.get("repo"), dict):
                r_dict = job_data["repo"]
                if r_dict.get("owner") and r_dict.get("name"):
                    candidates.append(f"{r_dict.get('owner')}/{r_dict.get('name')}")
            res_dict = job_data.get("result")
            if isinstance(res_dict, dict):
                candidates.extend([
                    res_dict.get("repo"),
                    res_dict.get("full_name"),
                    res_dict.get("repo_url"),
                    f"{res_dict.get('owner')}/{res_dict.get('name')}" if res_dict.get("owner") and res_dict.get("name") else None,
                ])
                analysis_meta = res_dict.get("analysis", {})
                if isinstance(analysis_meta, dict):
                    meta = analysis_meta.get("metadata", {})
                    if isinstance(meta, dict) and meta.get("owner") and meta.get("name"):
                        candidates.append(f"{meta.get('owner')}/{meta.get('name')}")

            if not any(normalize_repo_name(c) == target_norm for c in candidates if c):
                continue

            # Extract analysis payload
            analysis_raw = None
            arch_raw = None
            if isinstance(res_dict, dict) and "analysis" in res_dict:
                analysis_raw = res_dict["analysis"]
                arch_raw = res_dict.get("architecture")
            elif "analysis" in job_data:
                analysis_raw = job_data["analysis"]
                arch_raw = job_data.get("architecture")
            elif isinstance(res_dict, dict) and ("tech_stack" in res_dict or "structure" in res_dict):
                analysis_raw = res_dict
                arch_raw = job_data.get("architecture")

            if not analysis_raw:
                continue

            # Determine timestamp
            ts = 0.0
            for k in ("completed_at", "updated_at", "started_at", "created_at"):
                val = job_data.get(k)
                if val is not None:
                    try:
                        ts = float(val)
                        if ts > 0.0:
                            break
                    except (ValueError, TypeError):
                        pass
            if ts <= 0.0:
                try:
                    ts = os.path.getmtime(job_file)
                except Exception:
                    ts = 0.0

            if best_job is None or ts > best_timestamp:
                best_job = job_data
                best_timestamp = ts
                best_job_id = job_data.get("job_id") or fname.rsplit(".", 1)[0]
                best_analysis_raw = analysis_raw
                best_arch_raw = arch_raw

    if not best_job:
        return None

    try:
        if isinstance(best_analysis_raw, RepositoryAnalysis):
            analysis_obj = best_analysis_raw
        elif isinstance(best_analysis_raw, dict):
            analysis_obj = RepositoryAnalysis.model_validate(best_analysis_raw)
        else:
            analysis_obj = best_analysis_raw
    except Exception as exc:
        logger.warning("Could not validate recovered RepositoryAnalysis for %s: %s", target_repo, exc, exc_info=True)
        analysis_obj = best_analysis_raw

    try:
        if isinstance(best_arch_raw, ArchitectureSummary):
            architecture_obj = best_arch_raw
        elif isinstance(best_arch_raw, dict) and best_arch_raw:
            try:
                architecture_obj = ArchitectureSummary.model_validate(best_arch_raw)
            except Exception:
                relationships = [
                    ComponentRelationship(**r) if isinstance(r, dict) else r
                    for r in best_arch_raw.get("relationships", [])
                ]
                architecture_obj = ArchitectureSummary(
                    summary=best_arch_raw.get("summary", ""),
                    reading_order=best_arch_raw.get("reading_order", []),
                    relationships=relationships,
                )
        else:
            architecture_obj = ArchitectureSummary(
                summary="",
                reading_order=[],
                relationships=[],
            )
    except Exception as exc:
        logger.warning("Could not validate recovered ArchitectureSummary for %s: %s", target_repo, exc, exc_info=True)
        architecture_obj = ArchitectureSummary(
            summary="",
            reading_order=[],
            relationships=[],
        )

    store_entry = {
        "analysis": analysis_obj,
        "architecture": architecture_obj,
    }

    canonical_key = target_repo
    if hasattr(analysis_obj, "metadata") and isinstance(analysis_obj.metadata, dict):
        owner = analysis_obj.metadata.get("owner")
        name = analysis_obj.metadata.get("name")
        if owner and name:
            canonical_key = f"{owner}/{name}"
    elif isinstance(analysis_obj, dict) and "metadata" in analysis_obj and isinstance(analysis_obj["metadata"], dict):
        owner = analysis_obj["metadata"].get("owner")
        name = analysis_obj["metadata"].get("name")
        if owner and name:
            canonical_key = f"{owner}/{name}"

    dict.__setitem__(ANALYSIS_STORE, canonical_key, store_entry)
    if canonical_key != target_repo:
        dict.__setitem__(ANALYSIS_STORE, target_repo, store_entry)

    logger.info(
        "Recovered repository analysis for '%s' from completed job '%s' (timestamp=%.1f)",
        canonical_key,
        best_job_id,
        best_timestamp,
    )

    try:
        persist_analysis_store_sync()
        logger.info(
            "Successfully self-healed and persisted analysis store for '%s' from job '%s'",
            canonical_key,
            best_job_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to persist self-healed analysis store for '%s' (job=%s): %s",
            canonical_key,
            best_job_id,
            exc,
            exc_info=True,
        )

    return store_entry


class AnalysisStoreDict(dict):
    """Dynamic dict wrapper for ANALYSIS_STORE that reloads from disk on cache miss and falls back to completed jobs."""

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, str):
            _load_analysis_store(target_repo=key)
            if super().__contains__(key):
                return True
            for k in list(super().keys()):
                if k.lower() == key.lower():
                    return True
            recovered = recover_analysis_from_jobs(key)
            if recovered is not None:
                return True
        return False

    def __getitem__(self, key: Any) -> Any:
        if not super().__contains__(key) and isinstance(key, str):
            _load_analysis_store(target_repo=key)
            if not super().__contains__(key):
                for k in list(super().keys()):
                    if k.lower() == key.lower():
                        return super().__getitem__(k)
                recovered = recover_analysis_from_jobs(key)
                if recovered is not None:
                    return recovered
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        if not super().__contains__(key) and isinstance(key, str):
            _load_analysis_store(target_repo=key)
            if not super().__contains__(key):
                for k in list(super().keys()):
                    if k.lower() == key.lower():
                        return super().__getitem__(k)
                recovered = recover_analysis_from_jobs(key)
                if recovered is not None:
                    return recovered
        return super().get(key, default)


ANALYSIS_STORE: Dict[str, Dict[str, Any]] = AnalysisStoreDict()


def _load_disk_raw(path: str) -> Dict[str, Any]:
    """Safely load raw dict from disk store if it exists."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(
            "Could not read existing analysis store from %s: %s",
            path,
            exc,
            exc_info=True,
        )
        return {}


def _load_analysis_store(target_repo: Optional[str] = None) -> None:
    """Load persisted analysis data from disk into ANALYSIS_STORE."""
    global ANALYSIS_STORE

    store_path_env = os.environ.get("ANALYSIS_STORE_PATH")
    if store_path_env:
        candidate_paths = [store_path_env]
    else:
        store_path = _get_analysis_store_path()
        candidate_paths = [store_path]
        if store_path != "/app/data/analysis_store.json":
            candidate_paths.append("/app/data/analysis_store.json")
        if store_path != os.path.join("data", "analysis_store.json"):
            candidate_paths.append(os.path.join("data", "analysis_store.json"))

    for path in candidate_paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw: Dict[str, Any] = json.load(fh)
            for repo_name, entry in raw.items():
                if repo_name in dict(ANALYSIS_STORE) and target_repo != repo_name:
                    continue
                try:
                    analysis_data = RepositoryAnalysis.model_validate(entry["analysis"])
                    arch_raw = entry.get("architecture", {})
                    relationships = [
                        ComponentRelationship(**r)
                        for r in arch_raw.get("relationships", [])
                    ]
                    architecture_data = ArchitectureSummary(
                        summary=arch_raw.get("summary", ""),
                        reading_order=arch_raw.get("reading_order", []),
                        relationships=relationships,
                    )
                    dict.__setitem__(
                        ANALYSIS_STORE,
                        repo_name,
                        {
                            "analysis": analysis_data,
                            "architecture": architecture_data,
                        },
                    )
                except Exception as exc:
                    logger.debug(
                        "Skipping malformed store entry for '%s': %s", repo_name, exc
                    )
        except Exception as exc:
            logger.warning(
                "Could not read analysis store from %s: %s",
                path,
                exc,
                exc_info=True,
            )

    if target_repo:
        in_store = target_repo in dict(ANALYSIS_STORE) or any(
            k.lower() == target_repo.lower() for k in dict(ANALYSIS_STORE).keys()
        )
        if not in_store:
            recover_analysis_from_jobs(target_repo)


def _serialise_store(store_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Serialise an analysis store dict (or ANALYSIS_STORE) to a plain JSON-safe dict."""
    target = store_dict if store_dict is not None else ANALYSIS_STORE
    out: Dict[str, Any] = {}
    # Extract items snapshot to avoid concurrent dictionary mutation
    try:
        items = list(target.items()) if hasattr(target, "items") else []
    except Exception:
        items = []
    for repo_name, entry in items:
        if not isinstance(entry, dict):
            continue
        try:
            analysis_obj = entry.get("analysis")
            arch_obj = entry.get("architecture")
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
            logger.error(
                "Could not serialise store entry for '%s': %s",
                repo_name,
                exc,
                exc_info=True,
            )
    return out


def persist_analysis_store_sync(
    store: Optional[Dict[str, Any]] = None,
    store_path: Optional[str] = None,
) -> None:
    """Synchronously persist analysis store to disk using read-merge-write and inter-process locking."""
    from core.concurrency import interprocess_file_lock

    target_path = store_path or _get_analysis_store_path()
    lock_file = f"{target_path}.lock"

    try:
        with _persist_lock:
            with interprocess_file_lock(lock_file, timeout=30.0):
                # 1. Read existing disk store to preserve any other repository entries
                disk_data = _load_disk_raw(target_path)
                # 2. Serialize current in-memory entries snapshot
                source_store = store if store is not None else ANALYSIS_STORE
                mem_data = _serialise_store(source_store)
                # 3. Merge: in-memory entries take precedence or add to disk entries
                merged: Dict[str, Any] = {**disk_data, **mem_data}
                # 4. Atomically write the merged dictionary to disk
                _write_store_atomic(merged, target_path)
                logger.info(
                    "Analysis store persisted successfully (%d total entries) to %s.",
                    len(merged),
                    target_path,
                )
    except Exception as exc:
        logger.error(
            "Failed to persist analysis store to %s: %s",
            target_path,
            exc,
            exc_info=True,
        )
        raise


def _persist_analysis_store_sync(
    store: Optional[Dict[str, Any]] = None,
    store_path: Optional[str] = None,
) -> None:
    """Alias for persist_analysis_store_sync."""
    persist_analysis_store_sync(store=store, store_path=store_path)


async def _persist_analysis_store(
    store: Optional[Dict[str, Any]] = None,
    store_path: Optional[str] = None,
) -> None:
    """Async compatibility wrapper around synchronous thread-safe persistence."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, persist_analysis_store_sync, store, store_path)


def _write_store_atomic(
    payload: Dict[str, Any], store_path: Optional[str] = None
) -> None:
    """Write payload to active store path via atomic rename."""
    from core.concurrency import write_json_atomic

    target_path = store_path or _get_analysis_store_path()
    write_json_atomic(target_path, payload, indent=2)


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
        from services.symbol_service import SymbolService
        from services.architecture_service import ArchitectureService
        from services.call_graph_service import CallGraphService
        from services.git_history_service import GitHistoryService
        from services.api_surface_service import APISurfaceService

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
    from services.github_service import GitHubService

    return _get_or_create("github_service", lambda: GitHubService())


def get_embedding_service() -> EmbeddingService:
    from services.embedding_service import EmbeddingService

    return _get_or_create(
        "embedding_service",
        lambda: EmbeddingService(model_name=settings.embedding_model),
    )


def get_chroma_store() -> ChromaStore:
    from memory.chroma_store import ChromaStore

    return _get_or_create(
        "chroma_store",
        lambda: ChromaStore(persist_directory=settings.chroma_db_path),
    )


def get_qdrant_store() -> Optional[QdrantStore]:
    try:
        mod = sys.modules.get(__name__)
        qdrant_cls = getattr(mod, "QdrantStore", None) if mod else None
        if qdrant_cls is None:
            from memory.qdrant_store import QdrantStore

            qdrant_cls = QdrantStore

        return _get_or_create(
            "qdrant_store",
            lambda: qdrant_cls(
                url=settings.qdrant_url,
                grpc_port=settings.qdrant_grpc_port,
                prefer_grpc=settings.qdrant_prefer_grpc,
                api_key=settings.qdrant_api_key,
                timeout=settings.qdrant_timeout,
            ),
        )
    except (ImportError, Exception) as exc:
        logger.warning("Failed to initialize QdrantStore: %s", exc)
        return None


def get_vector_store() -> VectorStore:
    from memory.vector_store import ProductionVectorStore

    return _get_or_create(
        "vector_store",
        lambda: ProductionVectorStore(
            primary_store=(
                get_qdrant_store()
                if settings.vector_store_backend == "qdrant"
                else None
            ),
            fallback_store=get_chroma_store(),
            settings=settings,
            enable_fallback=settings.vector_store_enable_fallback,
        ),
    )


def get_chunker() -> CodeChunker:
    from services.chunking_service import CodeChunker

    return _get_or_create("chunker", lambda: CodeChunker())


def get_retrieval_service() -> RetrievalService:
    from services.retrieval_service import RetrievalService

    return _get_or_create(
        "retrieval_service",
        lambda: RetrievalService(
            embedding_service=get_embedding_service(),
            chroma_store=get_vector_store(),
        ),
    )


def get_architecture_service() -> ArchitectureService:
    from services.architecture_service import ArchitectureService

    return _get_or_create("architecture_service", lambda: ArchitectureService())


def get_graph_service() -> GraphService:
    from services.graph_service import GraphService

    return _get_or_create("graph_service", lambda: GraphService())


def get_graph_serializer() -> GraphSerializer:
    from services.graph_serializer import GraphSerializer

    return _get_or_create(
        "graph_serializer",
        lambda: GraphSerializer(
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_reading_order_service() -> ReadingOrderService:
    from services.reading_order_service import ReadingOrderService

    return _get_or_create(
        "reading_order_service",
        lambda: ReadingOrderService(architecture_service=get_architecture_service()),
    )


def get_impact_analysis_service() -> ImpactAnalysisService:
    from services.impact_analysis_service import ImpactAnalysisService

    return _get_or_create(
        "impact_analysis_service",
        lambda: ImpactAnalysisService(architecture_service=get_architecture_service()),
    )


def get_arch_context_service() -> ArchContextService:
    from services.arch_context_service import ArchContextService

    return _get_or_create(
        "arch_context_service",
        lambda: ArchContextService(architecture_service=get_architecture_service()),
    )


def get_symbol_service() -> SymbolService:
    from services.symbol_service import SymbolService

    return _get_or_create("symbol_service", lambda: SymbolService())


def get_pr_intelligence_service() -> PRIntelligenceService:
    from services.pr_intelligence_service import PRIntelligenceService

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
    from services.architecture_drift_service import ArchitectureDriftService

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
    from services.dead_code_service import DeadCodeService

    return _get_or_create(
        "dead_code_service",
        lambda: DeadCodeService(
            github_service=get_github_service(),
            graph_service=get_graph_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_git_history_service() -> GitHistoryService:
    from services.git_history_service import GitHistoryService

    return _get_or_create(
        "git_history_service",
        lambda: GitHistoryService(
            github_service=get_github_service(),
            graph_service=get_graph_service(),
        ),
    )


def get_call_graph_service() -> CallGraphService:
    from services.call_graph_service import CallGraphService

    return _get_or_create(
        "call_graph_service",
        lambda: CallGraphService(
            symbol_service=get_symbol_service(),
            graph_service=get_graph_service(),
        ),
    )


def get_api_surface_service() -> APISurfaceService:
    from services.api_surface_service import APISurfaceService

    return _get_or_create(
        "api_surface_service",
        lambda: APISurfaceService(
            symbol_service=get_symbol_service(),
            architecture_service=get_architecture_service(),
        ),
    )


def get_breaking_change_analyzer() -> Type[BreakingChangeAnalyzer]:
    from services.breaking_change_analyzer import BreakingChangeAnalyzer

    return BreakingChangeAnalyzer


def get_report_composer() -> ReportComposer:
    from services.report.composer import ReportComposer

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
    from services.report.renderer import HTMLRenderer

    return _get_or_create("html_renderer", lambda: HTMLRenderer())


def get_markdown_renderer() -> MarkdownRenderer:
    from services.report.renderer import MarkdownRenderer

    return _get_or_create("markdown_renderer", lambda: MarkdownRenderer())


def get_pdf_renderer() -> PDFRenderer:
    from services.report.renderer import PDFRenderer

    return _get_or_create("pdf_renderer", lambda: PDFRenderer())


def get_repository_twin_builder() -> RepositoryTwinBuilder:
    from services.twin_builder import RepositoryTwinBuilder

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
    from services.twin_navigator import RepositoryTwinNavigator

    return _get_or_create(
        "repository_twin_navigator", lambda: RepositoryTwinNavigator()
    )


def get_repository_knowledge_graph_builder() -> RepositoryKnowledgeGraphBuilder:
    from services.knowledge_graph_builder import RepositoryKnowledgeGraphBuilder

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
    from services.knowledge_graph_navigator import RepositoryKnowledgeGraphNavigator

    return _get_or_create(
        "repository_knowledge_graph_navigator",
        lambda: RepositoryKnowledgeGraphNavigator(
            builder=get_repository_knowledge_graph_builder()
        ),
    )


def get_structural_retrieval_engine() -> StructuralRetrievalEngine:
    from services.retrieval_engine import StructuralRetrievalEngine

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
    from services.reasoning_engine import EngineeringReasoningEngine

    return _get_or_create(
        "engineering_reasoning_engine",
        lambda: EngineeringReasoningEngine(),
    )


def get_graph_rag_service() -> GraphRAGService:
    from services.graph_rag import ChatPipeline, GraphRAGService

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
    from services.memory_service import EngineeringMemoryService

    return _get_or_create(
        "engineering_memory_service",
        lambda: EngineeringMemoryService(),
    )


def get_repository_inspector() -> RepositoryInspector:
    from services.repository_inspector import RepositoryInspector

    return _get_or_create(
        "repository_inspector",
        lambda: RepositoryInspector(),
    )


def get_continuous_monitoring_service() -> ContinuousMonitoringService:
    from services.continuous_monitoring import (
        ContinuousMonitoringService,
        ImmediatePolicy,
    )

    return _get_or_create(
        "continuous_monitoring_service",
        lambda: ContinuousMonitoringService(
            repository_inspector=get_repository_inspector(),
            default_policy=ImmediatePolicy(),
        ),
    )


def get_advisor_service() -> AdvisorService:
    from services.advisor import AdvisorService

    return _get_or_create("advisor_service", lambda: AdvisorService())


def get_execution_planner_service() -> ExecutionPlannerService:
    from services.execution_planner import ExecutionPlannerService

    return _get_or_create(
        "execution_planner_service",
        lambda: ExecutionPlannerService(),
    )


def get_workspace_service() -> WorkspaceService:
    from services.workspace import WorkspaceCoordinator, WorkspaceService

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


def get_retrieval_pipeline() -> Any:
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
            chroma_store=get_vector_store(),
            arch_context_service=get_arch_context_service(),
            intent_router=router,
        )

    return _get_or_create("retrieval_pipeline", _create_pipeline)


def get_service_by_class(cls: Type[Any]) -> Optional[Any]:
    from services.symbol_service import SymbolService
    from services.architecture_service import ArchitectureService
    from services.call_graph_service import CallGraphService
    from services.git_history_service import GitHistoryService
    from services.api_surface_service import APISurfaceService

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
    "qdrant_store": get_qdrant_store,
    "vector_store": get_vector_store,
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

_CLASS_EXPORTS = {
    "ChromaStore": ("memory.chroma_store", "ChromaStore"),
    "QdrantStore": ("memory.qdrant_store", "QdrantStore"),
    "VectorStore": ("memory.vector_store", "VectorStore"),
    "ProductionVectorStore": ("memory.vector_store", "ProductionVectorStore"),
    "GitHubService": ("services.github_service", "GitHubService"),
    "CodeChunker": ("services.chunking_service", "CodeChunker"),
    "EmbeddingService": ("services.embedding_service", "EmbeddingService"),
    "RetrievalService": ("services.retrieval_service", "RetrievalService"),
    "ArchitectureService": ("services.architecture_service", "ArchitectureService"),
    "GraphService": ("services.graph_service", "GraphService"),
    "ReadingOrderService": ("services.reading_order_service", "ReadingOrderService"),
    "ImpactAnalysisService": (
        "services.impact_analysis_service",
        "ImpactAnalysisService",
    ),
    "ArchContextService": ("services.arch_context_service", "ArchContextService"),
    "GraphSerializer": ("services.graph_serializer", "GraphSerializer"),
    "SymbolService": ("services.symbol_service", "SymbolService"),
    "PRIntelligenceService": (
        "services.pr_intelligence_service",
        "PRIntelligenceService",
    ),
    "ArchitectureDriftService": (
        "services.architecture_drift_service",
        "ArchitectureDriftService",
    ),
    "DeadCodeService": ("services.dead_code_service", "DeadCodeService"),
    "GitHistoryService": ("services.git_history_service", "GitHistoryService"),
    "CallGraphService": ("services.call_graph_service", "CallGraphService"),
    "APISurfaceService": ("services.api_surface_service", "APISurfaceService"),
    "BreakingChangeAnalyzer": (
        "services.breaking_change_analyzer",
        "BreakingChangeAnalyzer",
    ),
    "ReportComposer": ("services.report.composer", "ReportComposer"),
    "HTMLRenderer": ("services.report.renderer", "HTMLRenderer"),
    "MarkdownRenderer": ("services.report.renderer", "MarkdownRenderer"),
    "PDFRenderer": ("services.report.renderer", "PDFRenderer"),
    "RepositoryTwinBuilder": ("services.twin_builder", "RepositoryTwinBuilder"),
    "RepositoryTwinNavigator": ("services.twin_navigator", "RepositoryTwinNavigator"),
    "RepositoryKnowledgeGraphBuilder": (
        "services.knowledge_graph_builder",
        "RepositoryKnowledgeGraphBuilder",
    ),
    "RepositoryKnowledgeGraphNavigator": (
        "services.knowledge_graph_navigator",
        "RepositoryKnowledgeGraphNavigator",
    ),
    "StructuralRetrievalEngine": (
        "services.retrieval_engine",
        "StructuralRetrievalEngine",
    ),
    "EngineeringReasoningEngine": (
        "services.reasoning_engine",
        "EngineeringReasoningEngine",
    ),
    "ChatPipeline": ("services.graph_rag", "ChatPipeline"),
    "GraphRAGService": ("services.graph_rag", "GraphRAGService"),
    "EngineeringMemoryService": ("services.memory_service", "EngineeringMemoryService"),
    "RepositoryInspector": ("services.repository_inspector", "RepositoryInspector"),
    "ContinuousMonitoringService": (
        "services.continuous_monitoring",
        "ContinuousMonitoringService",
    ),
    "ImmediatePolicy": ("services.continuous_monitoring", "ImmediatePolicy"),
    "AdvisorService": ("services.advisor", "AdvisorService"),
    "ExecutionPlannerService": (
        "services.execution_planner",
        "ExecutionPlannerService",
    ),
    "WorkspaceCoordinator": ("services.workspace", "WorkspaceCoordinator"),
    "WorkspaceService": ("services.workspace", "WorkspaceService"),
}


def __getattr__(name: str) -> Any:
    if name in _GETTERS:
        return _GETTERS[name]()
    if name in _CLASS_EXPORTS:
        mod_name, attr_name = _CLASS_EXPORTS[name]
        import importlib

        mod = importlib.import_module(mod_name)
        return getattr(mod, attr_name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
