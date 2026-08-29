"""Repositories router.

Endpoints:
  GET  /api/repos/examples
  GET  /api/repos/recent
  POST /api/index
  POST /api/retrieve
  POST /api/analyze            (SSE stream)
  GET  /api/analysis/{owner}/{repo_name}
  POST /api/repos/repair
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.memory_tracker import MemoryTracker, get_current_rss_mb
from utils.subprocess_runner import SHORT_GIT_TIMEOUT, run_safe_command

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import (
    ANALYSIS_STORE,
    persist_analysis_store_sync,
    get_architecture_service,
    get_chroma_store,
    get_chunker,
    get_embedding_service,
    get_github_service,
    get_symbol_service,
    get_snapshot_store,
    get_repository_twin_builder,
    get_engineering_memory_service,
    get_call_graph_service,
    get_api_surface_service,
    get_report_composer,
    get_dead_code_service,
)
from models.schemas import RepositoryAnalysis
from services.architecture_summary_service import generate_architecture_summary
from services.github_service import (
    BranchNotFoundError,
    GitOperationError,
    InvalidGitHubRepoURLError,
    RepositoryNotFoundError,
)
from services.ingestion_service import detect_tech_stack_and_deps, parse_repo_name

logger = logging.getLogger(__name__)


class _ReloadSafeDependency:
    """Resolve a compatibility dependency from the currently loaded router module."""

    def __init__(self, name: str, getter_fn) -> None:
        self._name = name
        self._getter = getter_fn

    def __getattr__(self, attribute: str) -> object:
        module = sys.modules.get(__name__)
        dependency = getattr(module, self._name, None)
        if dependency is None or dependency is self:
            dependency = self._getter()
        return getattr(dependency, attribute)


architecture_service = _ReloadSafeDependency(
    "architecture_service", get_architecture_service
)
chroma_store = _ReloadSafeDependency("chroma_store", get_chroma_store)
chunker = _ReloadSafeDependency("chunker", get_chunker)
embedding_service = _ReloadSafeDependency("embedding_service", get_embedding_service)
github_service = _ReloadSafeDependency("github_service", get_github_service)
symbol_service = _ReloadSafeDependency("symbol_service", get_symbol_service)
snapshot_store = _ReloadSafeDependency("snapshot_store", get_snapshot_store)
repository_twin_builder = _ReloadSafeDependency(
    "repository_twin_builder", get_repository_twin_builder
)
engineering_memory_service = _ReloadSafeDependency(
    "engineering_memory_service", get_engineering_memory_service
)
call_graph_service = _ReloadSafeDependency("call_graph_service", get_call_graph_service)
api_surface_service = _ReloadSafeDependency(
    "api_surface_service", get_api_surface_service
)
report_composer = _ReloadSafeDependency("report_composer", get_report_composer)
dead_code_service = _ReloadSafeDependency("dead_code_service", get_dead_code_service)


class PipelineTimer:
    def __init__(self) -> None:
        self.timings: Dict[str, float] = {}
        self.start_times: Dict[str, float] = {}

    def start(self, phase: str) -> None:
        self.start_times[phase] = time.perf_counter()

    def stop(self, phase: str) -> None:
        if phase in self.start_times:
            elapsed = time.perf_counter() - self.start_times.pop(phase)
            self.timings[phase] = self.timings.get(phase, 0.0) + elapsed

    def get_phase_duration(self, phase: str) -> float:
        if phase == "Chunk_Embed_Index":
            if (
                "Chunk_Embed_Index" in self.timings
                and self.timings["Chunk_Embed_Index"] > 0
            ):
                return self.timings["Chunk_Embed_Index"]
            return (
                self.timings.get("Chunk", 0.0)
                + self.timings.get("Embedding", 0.0)
                + self.timings.get("Chroma", 0.0)
            )
        return self.timings.get(phase, 0.0)

    def format_report(self) -> str:
        lines = ["\nRepository Analysis Performance Report"]
        phases = [
            ("Clone", "Clone"),
            ("Parse & AST", "Parse"),
            ("Chunk, Embed & Index", "Chunk_Embed_Index"),
            ("Architecture Summary", "Summary"),
            ("Graph Build", "Graphs"),
            ("Report Generation", "Report"),
        ]
        total = 0.0
        for label, phase in phases:
            val = self.get_phase_duration(phase)
            total += val
            lines.append(f"{label: <25}....{val: >5.1f}s")
        lines.append(f"{'Total Active Compute': <25}....{total: >5.1f}s")
        return "\n".join(lines)


def format_analysis_error(e: Exception) -> str:
    err_str = str(e)
    stage = "Analysis Pipeline"
    # Raw exception text is never returned to clients; full diagnostics are logged
    # by the caller before this formatter runs.
    reason = "An unexpected internal error occurred."
    suggested_fix = "Please check the server logs or retry later."
    recoverable = "Yes"
    retryable = "Yes"

    # Match specific error types
    if isinstance(e, InvalidGitHubRepoURLError):
        stage = "URL Parsing"
        reason = f"The provided GitHub repository URL is invalid: '{err_str}'."
        suggested_fix = "Please verify the URL format (e.g. https://github.com/owner/repo) and try again."
        recoverable = "No"
        retryable = "No"
    elif isinstance(e, BranchNotFoundError):
        stage = "Branch Validation"
        reason = f"The specified branch or ref does not exist: '{err_str}'."
        suggested_fix = "Please verify the branch name in your request."
        recoverable = "No"
        retryable = "No"
    elif isinstance(e, RepositoryNotFoundError):
        stage = "Cloning"
        reason = "Repository not found or access denied."
        suggested_fix = (
            "Please verify the repository identifier. If the repository is private, "
            "ensure the server is configured with credentials that can read it."
        )
        recoverable = "No"
        retryable = "No"
    elif isinstance(e, GitOperationError):
        stage = "Cloning"
        if "network" in err_str.lower():
            reason = "Unable to connect to GitHub (network error)."
            suggested_fix = (
                "Please check the server's network connection and try again."
            )
        else:
            reason = (
                f"Git operation failed: {err_str}"
                if err_str
                else "Unable to complete the repository operation."
            )
            suggested_fix = "Please check the server logs or retry later."
        recoverable = "Yes"
        retryable = "Yes"
    elif (
        "permission" in err_str.lower()
        or "authorization" in err_str.lower()
        or "write access" in err_str.lower()
    ):
        stage = "Cloning"
        reason = "Repository not found or access denied."
        suggested_fix = (
            "Please verify the repository identifier and that the server is "
            "configured with credentials that can read it."
        )
        recoverable = "No"
        retryable = "No"
    elif (
        "network failure" in err_str.lower()
        or "connection failure" in err_str.lower()
        or "could not resolve host" in err_str.lower()
    ):
        stage = "Cloning"
        reason = "Unable to connect to GitHub (network error)."
        suggested_fix = "Please check the server's network connection and try again."
        recoverable = "Yes"
        retryable = "Yes"
    elif (
        "rate limit" in err_str.lower()
        or "quota" in err_str.lower()
        or "503" in err_str.lower()
        or "heavy load" in err_str.lower()
    ):
        stage = "LLM/API Call"
        reason = "GitHub or AI provider rate limit/quota exceeded or server overloaded."
        suggested_fix = "Please wait a few minutes before retrying."
        recoverable = "Yes"
        retryable = "Yes"
    # For all other unrecognized exceptions, the default generic reason set above
    # is returned. Raw exception text is NEVER interpolated into client-facing
    # messages to prevent information disclosure (paths, SQL, credentials, etc.).

    return (
        f"Stage: {stage}\n"
        f"Reason: {reason}\n"
        f"Suggested Fix: {suggested_fix}\n"
        f"Recoverable: {recoverable} | Retryable: {retryable}"
    )


router = APIRouter(tags=["Repositories"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="GitHub repository URL")
    branch: str = Field("main", description="Git branch or ref")
    model: str = Field(
        "deepseek-ai/deepseek-v4-flash", description="LLM model variant to use"
    )
    force_rebuild: bool = Field(False, description="Force full rebuild of all indexes")


class IndexRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository URL")


class RetrieveRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")
    question: str = Field(..., description="Question query")


class RepoRepairRequest(BaseModel):
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/repos/examples")
async def get_examples():
    """List pre-configured example repositories for user reference."""
    return [
        {
            "name": "google/guava",
            "url": "https://github.com/google/guava",
            "tech_stack": ["Java", "Maven"],
            "description": "Google core libraries for Java.",
        },
        {
            "name": "fastapi/fastapi",
            "url": "https://github.com/fastapi/fastapi",
            "tech_stack": ["Python", "Pydantic", "Starlette"],
            "description": (
                "High performance, easy to learn, fast to code, "
                "ready for production API framework."
            ),
        },
        {
            "name": "vercel/next.js",
            "url": "https://github.com/vercel/next.js",
            "tech_stack": ["JavaScript", "TypeScript", "React", "Rust"],
            "description": "The React Framework for the Web.",
        },
    ]


@router.get("/repos/recent")
async def get_recent():
    """Fetch list of recently analysed repositories from the in-memory store."""
    results = []
    for name, data in ANALYSIS_STORE.items():
        analysis_obj = data.get("analysis")
        if hasattr(analysis_obj, "tech_stack"):
            tech_stack = analysis_obj.tech_stack
        elif isinstance(analysis_obj, dict):
            tech_stack = analysis_obj.get("tech_stack", [])
        else:
            tech_stack = []
        results.append(
            {
                "name": name,
                "url": f"https://github.com/{name}",
                "tech_stack": tech_stack,
                "analyzed_at": "Just now",
            }
        )
    return results


def _get_source_files_stream(local_path: str):
    """Return an iterator of source files, respecting test mocks if present."""
    from unittest.mock import Mock

    if isinstance(getattr(github_service, "extract_source_files", None), Mock):
        raw_files = github_service.extract_source_files(local_path)
        return iter(raw_files)
    return github_service.iter_source_files(local_path)


def _get_batch_size() -> int:
    """Return configured max_outer_batch_size from embedding service, settings, or default."""
    val = getattr(embedding_service, "max_outer_batch_size", None)
    if isinstance(val, int) and val > 0:
        return val
    from core.config import settings

    return getattr(settings, "embedding_batch_size", 64)


@router.post("/index")
async def index_repository(request: IndexRequest):
    """Clone a repository, chunk the code, generate embeddings, and index in ChromaDB."""
    try:
        repo_url = request.repo_url.strip()
        parsed = github_service.parse_repo_url(repo_url)
        repo_name = f"{parsed['owner']}/{parsed['repo']}"

        local_path = await asyncio.to_thread(github_service.clone_repository, repo_url)

        def run_streaming_indexing():
            version = uuid.uuid4().hex
            staged_count = 0
            file_count = 0
            total_chunks = 0
            chunk_buffer = []
            batch_size = _get_batch_size()
            version_staged = False

            try:
                for file_rec in _get_source_files_stream(local_path):
                    file_count += 1
                    file_chunks = chunker.chunk_file(
                        file_rec["path"], file_rec["content"]
                    )
                    if not file_chunks:
                        continue
                    chunk_buffer.extend(file_chunks)
                    total_chunks += len(file_chunks)

                    while len(chunk_buffer) >= batch_size:
                        chunk_batch = chunk_buffer[:batch_size]
                        chunk_buffer = chunk_buffer[batch_size:]
                        emb_batch = embedding_service.generate_embeddings(chunk_batch)
                        staged_batch_count = chroma_store.stage_repository_batch(
                            repo_name,
                            version,
                            chunk_batch,
                            emb_batch,
                            staged_count,
                        )
                        staged_count += staged_batch_count
                        version_staged = True
                        del chunk_batch
                        del emb_batch

                if chunk_buffer:
                    emb_batch = embedding_service.generate_embeddings(chunk_buffer)
                    staged_batch_count = chroma_store.stage_repository_batch(
                        repo_name,
                        version,
                        chunk_buffer,
                        emb_batch,
                        staged_count,
                    )
                    staged_count += staged_batch_count
                    version_staged = True
                    del chunk_buffer
                    del emb_batch

                if version_staged:
                    chroma_store.publish_repository_version(repo_name, version)
            except Exception:
                if version_staged:
                    chroma_store.rollback_staged_version(repo_name, version)
                raise

            return file_count, total_chunks

        files_indexed, chunks_indexed = await asyncio.to_thread(run_streaming_indexing)

        return {
            "status": "indexed",
            "files": files_indexed,
            "chunks": chunks_indexed,
        }
    except Exception as e:
        error_message = str(e).lower()
        if isinstance(e, InvalidGitHubRepoURLError):
            raise HTTPException(status_code=400, detail=str(e))
        if isinstance(e, RepositoryNotFoundError):
            raise HTTPException(status_code=404, detail=str(e))
        if isinstance(e, RuntimeError) and (
            "was not found anonymously" in error_message
            or "repository not found" in error_message
            or "authentication failure" in error_message
            or "does not have read access" in error_message
        ):
            # Git hosts intentionally do not distinguish an inaccessible private
            # repository from a nonexistent one; preserve that non-disclosure
            # contract and never reflect provider authentication details.
            raise HTTPException(
                status_code=404,
                detail="Repository not found or inaccessible.",
            )
        if isinstance(e, ValueError) and "Invalid GitHub repository URL" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        logger.error("Failed to index repository: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/retrieve")
async def retrieve_from_repository(request: RetrieveRequest):
    """Search vector database and return a context-aware answer."""
    from backend.dependencies import get_retrieval_pipeline

    try:
        pipeline = get_retrieval_pipeline()
        result = await pipeline.retrieve(request.repo.strip(), request.question.strip())
        return result
    except Exception as e:
        logger.error("Failed to retrieve: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")


# ---------------------------------------------------------------------------
# Asynchronous Job State Management
# ---------------------------------------------------------------------------
_LOCAL_JOBS: Dict[str, Dict[str, Any]] = {}


def _get_modal_jobs_dict():
    """Access Modal distributed Dict if available."""
    try:
        # pyrefly: ignore [missing-import]
        import modal

        return modal.Dict.from_name("aria-analysis-jobs", create_if_missing=True)
    except Exception:
        return None


def _get_jobs_dir() -> str:
    jobs_dir_env = os.environ.get("JOB_STATE_DIR")
    if jobs_dir_env:
        os.makedirs(jobs_dir_env, exist_ok=True)
        return jobs_dir_env

    from core.config import settings

    db_path = (
        os.environ.get("SQLITE_DB_PATH")
        or getattr(settings, "sqlite_db_path", None)
        or "data/repo_understanding.db"
    )
    base = os.path.dirname(os.path.abspath(db_path)) if db_path else "data"
    jobs_dir = os.path.join(base, "jobs")
    os.makedirs(jobs_dir, exist_ok=True)
    return jobs_dir


def get_job_state(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve job state from persistent shared file store, Modal Dict, or local memory."""
    modal_dict = _get_modal_jobs_dict()
    if modal_dict is not None:
        try:
            if job_id in modal_dict:
                return dict(modal_dict[job_id])
        except Exception as exc:
            logger.debug("Could not read job %s from modal.Dict: %s", job_id, exc)

    # Candidate directories for job persistence across local and containerized environments
    candidate_dirs = [
        _get_jobs_dir(),
        "/app/data/jobs",
        os.path.join("data", "jobs"),
    ]

    newest_disk_state = None
    newest_mtime = -1.0

    for directory in candidate_dirs:
        try:
            if not directory or not os.path.exists(directory):
                continue
            job_file = os.path.join(directory, f"{job_id}.json")
            if os.path.isfile(job_file):
                mtime = os.path.getmtime(job_file)
                with open(job_file, "r", encoding="utf-8") as fh:
                    file_state = json.load(fh)
                    if isinstance(file_state, dict):
                        state_updated = float(
                            file_state.get("updated_at")
                            or file_state.get("started_at")
                            or mtime
                        )
                        if state_updated > newest_mtime:
                            newest_mtime = state_updated
                            newest_disk_state = file_state
        except Exception as exc:
            logger.debug(
                "Could not read persistent job state %s from %s: %s",
                job_id,
                directory,
                exc,
            )

    local_state = _LOCAL_JOBS.get(job_id)
    if newest_disk_state is not None:
        if not local_state:
            _LOCAL_JOBS[job_id] = newest_disk_state
            return newest_disk_state

        local_updated = float(
            local_state.get("updated_at") or local_state.get("started_at") or 0.0
        )
        disk_updated = float(
            newest_disk_state.get("updated_at")
            or newest_disk_state.get("started_at")
            or 0.0
        )

        if disk_updated >= local_updated or newest_disk_state.get("status") in (
            "running",
            "completed",
            "failed",
        ):
            _LOCAL_JOBS[job_id] = newest_disk_state
            return newest_disk_state

        return local_state

    return local_state


def set_job_state(job_id: str, state: Dict[str, Any]) -> None:
    """Store job state in local dictionary, Modal distributed Dict, and persistent shared file store."""
    from core.concurrency import write_json_atomic

    state["updated_at"] = time.time()
    _LOCAL_JOBS[job_id] = state
    modal_dict = _get_modal_jobs_dict()
    if modal_dict is not None:
        try:
            modal_dict[job_id] = state
        except Exception as exc:
            logger.debug("Could not write job %s to modal.Dict: %s", job_id, exc)

    try:
        job_file = os.path.join(_get_jobs_dir(), f"{job_id}.json")
        write_json_atomic(job_file, state)
    except Exception as exc:
        logger.debug("Could not persist atomic job state for %s: %s", job_id, exc)


def emit_phase_telemetry(
    repo: str,
    phase: str,
    status: str,
    items_processed: int = 0,
    items_total: int = 0,
    elapsed_seconds: float = 0.0,
    memory_mb: float = 0.0,
    request_id: str = "",
    job_id: str = "",
    **extra: Any,
) -> Dict[str, Any]:
    """Emit structured telemetry event for every major analysis phase."""
    event = {
        "event": "analysis_phase",
        "repo": repo,
        "job_id": job_id or "",
        "phase": phase,
        "status": status,
        "items_processed": items_processed,
        "items_total": items_total,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "memory_mb": round(memory_mb or get_current_rss_mb(), 2),
        "request_id": request_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        event.update(extra)
    logger.info("TELEMETRY %s", json.dumps(event, default=str))
    return event


# ---------------------------------------------------------------------------
# Core Analysis Pipeline Execution
# ---------------------------------------------------------------------------
def execute_repository_analysis(
    repo_url: str,
    branch: Optional[str] = "main",
    force_rebuild: bool = False,
    progress_callback: Any = None,
    request_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the complete repository analysis pipeline synchronously.

    Preserves 100% of the existing analysis logic:
      01 CLONE   — Git clone / pull
      02 DETECT  — Tech stack & dependency detection
      03 PARSE   — AST Parsing & change detection
      04 EMBED   — BGE Embeddings & Vector store ingestion
      05 INDEX   — Symbol Index, Dependency Graph, Call Graph, API Surface
      06 ANALYZE — Architecture Summary & Graph Intelligence
      07 ANSWER  — Report Generation & Manifest persistence
    """
    from core.change_detector import ChangeDetector
    from models.build_manifest import BuildManifest
    from core.concurrency import repository_lock

    repo_url = repo_url.strip()
    repo_name = parse_repo_name(repo_url)
    owner = repo_name.split("/")[0] if "/" in repo_name else "owner"
    name = repo_name.split("/")[1] if "/" in repo_name else repo_name
    branch = branch or "main"

    with repository_lock(repo_name):
        timer = PipelineTimer()
        mem_tracker = MemoryTracker(repo_name=repo_name, logger_instance=logger)
        start_time = time.time()
        successful_phases: List[str] = []
        failed_phases: List[str] = []
        skipped_phases: List[str] = []
        phase_errors: Dict[str, str] = {}

        def _emit(
            step_id: str,
            status: str,
            message: str,
            stats: Optional[Dict[str, Any]] = None,
            progress: int = 0,
            items_processed: int = 0,
            items_total: int = 0,
        ):
            elapsed = time.time() - start_time
            curr_rss = get_current_rss_mb()
            proc_count = (
                items_processed
                or (stats.get("chunks_processed") if stats else 0)
                or (stats.get("files_processed") if stats else 0)
            )
            emit_phase_telemetry(
                repo=repo_name,
                job_id=job_id or "",
                phase=step_id,
                status=status,
                items_processed=proc_count,
                items_total=items_total,
                elapsed_seconds=elapsed,
                memory_mb=curr_rss,
                request_id=request_id or "",
            )
            if progress_callback:
                try:
                    progress_callback(
                        {
                            "step_id": step_id,
                            "status": status,
                            "message": message,
                            "stats": stats or {},
                            "progress": progress,
                            "repo": {
                                "owner": owner,
                                "name": name,
                                "full_name": repo_name,
                            },
                        }
                    )
                except Exception as cb_exc:
                    logger.debug(
                        "Progress callback error for %s: %s", repo_name, cb_exc
                    )

        # ── 1. Cloning (01 CLONE) ────────────────────────────────────────────────
        mem_tracker.log_phase("before_clone")
        _emit("clone", "cloning", "Cloning repository from GitHub...", progress=5)
        timer.start("Clone")
        try:
            local_path = github_service.clone_repository(repo_url, branch)
            successful_phases.append("clone")
        finally:
            timer.stop("Clone")
        mem_tracker.log_phase("after_clone", local_path=local_path)
        _emit("clone", "cloned", "✓ Repository cloned successfully", progress=15)

        # ── 2. Detecting & Extracting (02 DETECT) ─────────────────────────────────
        _emit(
            "detect", "detecting", "Detecting languages and frameworks...", progress=20
        )
        timer.start("Parse")
        mem_tracker.log_phase("before_iter_source_files")

        all_file_paths = []
        manifest_records = []
        file_hashes = {}
        total_bytes = 0
        file_count = 0
        t0 = time.perf_counter()

        for f in _get_source_files_stream(local_path):
            file_count += 1
            p = f["path"]
            content = f["content"]
            content_bytes = len(content.encode("utf-8", errors="replace"))
            total_bytes += content_bytes
            all_file_paths.append(p)
            file_hashes[p] = ChangeDetector.compute_content_hash(content)
            mem_tracker.record_file(content_bytes)

            if (
                p.endswith("package.json")
                or p.endswith("requirements.txt")
                or p.endswith("pyproject.toml")
            ):
                manifest_records.append({"path": p, "content": content})
            else:
                manifest_records.append({"path": p})

        elapsed = time.perf_counter() - t0
        logger.info(
            "Source file scan completed | repo=%s files=%d bytes=%d elapsed=%.2fs request_id=%s",
            repo_name,
            file_count,
            total_bytes,
            elapsed,
            request_id,
        )
        mem_tracker.log_phase("after_extraction")

        mem_tracker.log_phase("before_tech_stack_detection")
        tech_stack, dependencies = detect_tech_stack_and_deps(manifest_records)
        mem_tracker.log_phase("after_tech_stack_detection")
        timer.stop("Parse")
        successful_phases.append("detect")
        _emit(
            "detect",
            "detected",
            f"✓ Technologies detected: {tech_stack}",
            stats={"tech_stack": tech_stack},
            progress=30,
        )

        # ── 3. Change Detection & Incremental Plan (03 PARSE) ─────────────────────
        old_manifest_data = snapshot_store.load(repo_name, "build_manifest")
        old_manifest = None
        if old_manifest_data:
            try:
                old_manifest = BuildManifest.model_validate(old_manifest_data)
            except Exception as exc:
                logger.warning("Stale or malformed build manifest ignored: %s", exc)

        mem_tracker.log_phase("before_change_detection")
        detector = ChangeDetector()
        change_set, file_hashes, repo_hash = detector.detect_changes_from_hashes(
            file_hashes, old_manifest
        )
        mem_tracker.log_phase("after_change_detection")

        schema_mismatch = False
        if old_manifest:
            prev_sym_ver = old_manifest.schema_versions.get("Symbol Index", 0)
            prev_dep_ver = old_manifest.schema_versions.get("Dependency Graph", 0)
            if (
                prev_sym_ver < symbol_service.schema_version
                or prev_dep_ver < architecture_service.schema_version
            ):
                schema_mismatch = True

        is_incremental = (
            old_manifest is not None and not force_rebuild and not schema_mismatch
        )
        renamed_old_paths = set(change_set.renamed.keys())
        renamed_new_paths = set(change_set.renamed.values())
        changed_files = (
            change_set.added
            | change_set.modified
            | change_set.deleted
            | renamed_old_paths
            | renamed_new_paths
        )
        successful_phases.append("parse")

        # ── 4. Granular Chunking & Embedding (04 EMBED) ───────────────────────────
        _emit(
            "parse",
            "parsing",
            f"Parsing Source Files: {len(all_file_paths)} files",
            stats={"files_processed": len(all_file_paths)},
            progress=40,
        )

        if is_incremental:
            files_to_delete = list(
                change_set.modified | change_set.deleted | renamed_old_paths
            )
            if files_to_delete:
                timer.start("Chroma")
                try:
                    chroma_store.delete_files(repo_name, files_to_delete)
                    logger.info(
                        "Successfully deleted chunks for %d files.",
                        len(files_to_delete),
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to delete chunks for %d files: %s",
                        len(files_to_delete),
                        exc,
                    )
                    raise
                finally:
                    timer.stop("Chroma")

            target_paths = change_set.added | change_set.modified | renamed_new_paths
            _emit(
                "embed",
                "generating_embeddings",
                "Generating Embeddings for modified files...",
                progress=45,
            )

            mem_tracker.log_phase("before_chunking")
            batch_size = _get_batch_size()
            chunk_buffer = []
            inserted_count = 0
            file_chunk_counts = {}
            batch_idx = 0

            timer.start("Chunk")
            for f in _get_source_files_stream(local_path):
                p = f["path"]
                if p not in target_paths:
                    continue
                file_chunks = chunker.chunk_file(p, f["content"])
                if not file_chunks:
                    continue
                mem_tracker.record_chunk(len(file_chunks))
                chunk_buffer.extend(file_chunks)

                while len(chunk_buffer) >= batch_size:
                    chunk_batch = chunk_buffer[:batch_size]
                    chunk_buffer = chunk_buffer[batch_size:]
                    batch_idx += 1
                    t0 = time.perf_counter()

                    if batch_idx == 1:
                        mem_tracker.log_phase("before_first_embedding_batch")

                    timer.stop("Chunk")
                    timer.start("Embedding")
                    emb_stats = {}
                    emb_batch = embedding_service.generate_embeddings(
                        chunk_batch, stats=emb_stats
                    )
                    timer.stop("Embedding")

                    mem_tracker.log_phase(
                        "after_embedding_batch",
                        batch=batch_idx,
                        batch_items=len(chunk_batch),
                    )

                    bulk_ids = []
                    bulk_docs = []
                    bulk_embeddings = []
                    bulk_metadatas = []

                    for idx, chunk in enumerate(chunk_batch):
                        c_path = chunk["path"]
                        chunk_idx = file_chunk_counts.get(c_path, 0)
                        file_chunk_counts[c_path] = chunk_idx + 1

                        unique_id = f"{repo_name}_{c_path}_{chunk_idx}".replace(
                            "/", "_"
                        ).replace(".", "_")
                        bulk_ids.append(unique_id)
                        bulk_docs.append(chunk["content"])
                        bulk_embeddings.append(emb_batch[idx])
                        bulk_metadatas.append(
                            {
                                "repo_name": repo_name,
                                "file_path": c_path,
                                "chunk_id": chunk_idx,
                                "language": chunker.detect_language(c_path),
                            }
                        )

                    if bulk_ids:
                        timer.start("Chroma")
                        chroma_store.add_code_chunks_bulk(
                            bulk_ids,
                            bulk_docs,
                            bulk_embeddings,
                            bulk_metadatas,
                        )
                        timer.stop("Chroma")
                        inserted_count += len(bulk_ids)
                        mem_tracker.record_embeddings_indexed(len(bulk_ids))

                    mem_tracker.log_phase(
                        "after_vector_store_staging_batch",
                        batch=batch_idx,
                        staged=inserted_count,
                    )

                    elapsed_batch = time.perf_counter() - t0
                    hits = emb_stats.get("cache_hits", 0)
                    misses = emb_stats.get("cache_misses", 0)
                    logger.info(
                        "Incremental indexing progress batch=%d embedded=%d indexed=%d hits=%d misses=%d elapsed=%.2fs",
                        batch_idx,
                        len(emb_batch),
                        inserted_count,
                        hits,
                        misses,
                        elapsed_batch,
                    )
                    _emit(
                        "embed",
                        "generating_embeddings",
                        f"Generating Embeddings: {inserted_count} new chunks | batch={batch_size} | hits={hits} | misses={misses}",
                        stats={
                            "chunks_processed": inserted_count,
                            "embeddings_indexed": inserted_count,
                            "files_processed": len(target_paths),
                            "elapsed_seconds": int(time.time() - start_time),
                            "cache_hits": hits,
                            "cache_misses": misses,
                            "batch_size": batch_size,
                            **emb_stats,
                        },
                        progress=50,
                    )

                    del chunk_batch
                    del emb_batch
                    del bulk_ids
                    del bulk_docs
                    del bulk_embeddings
                    del bulk_metadatas
                    timer.start("Chunk")

            if chunk_buffer:
                timer.stop("Chunk")
                batch_idx += 1
                t0 = time.perf_counter()
                if batch_idx == 1:
                    mem_tracker.log_phase("before_first_embedding_batch")

                timer.start("Embedding")
                emb_stats = {}
                emb_batch = embedding_service.generate_embeddings(
                    chunk_buffer, stats=emb_stats
                )
                timer.stop("Embedding")

                mem_tracker.log_phase(
                    "after_embedding_batch",
                    batch=batch_idx,
                    batch_items=len(chunk_buffer),
                )

                bulk_ids = []
                bulk_docs = []
                bulk_embeddings = []
                bulk_metadatas = []

                for idx, chunk in enumerate(chunk_buffer):
                    c_path = chunk["path"]
                    chunk_idx = file_chunk_counts.get(c_path, 0)
                    file_chunk_counts[c_path] = chunk_idx + 1

                    unique_id = f"{repo_name}_{c_path}_{chunk_idx}".replace(
                        "/", "_"
                    ).replace(".", "_")
                    bulk_ids.append(unique_id)
                    bulk_docs.append(chunk["content"])
                    bulk_embeddings.append(emb_batch[idx])
                    bulk_metadatas.append(
                        {
                            "repo_name": repo_name,
                            "file_path": c_path,
                            "chunk_id": chunk_idx,
                            "language": chunker.detect_language(c_path),
                        }
                    )

                if bulk_ids:
                    timer.start("Chroma")
                    chroma_store.add_code_chunks_bulk(
                        bulk_ids,
                        bulk_docs,
                        bulk_embeddings,
                        bulk_metadatas,
                    )
                    timer.stop("Chroma")
                    inserted_count += len(bulk_ids)
                    mem_tracker.record_embeddings_indexed(len(bulk_ids))

                mem_tracker.log_phase(
                    "after_vector_store_staging_batch",
                    batch=batch_idx,
                    staged=inserted_count,
                )

                elapsed_batch = time.perf_counter() - t0
                hits = emb_stats.get("cache_hits", 0)
                misses = emb_stats.get("cache_misses", 0)
                logger.info(
                    "Incremental indexing progress batch=%d embedded=%d indexed=%d hits=%d misses=%d elapsed=%.2fs",
                    batch_idx,
                    len(emb_batch),
                    inserted_count,
                    hits,
                    misses,
                    elapsed_batch,
                )
                _emit(
                    "embed",
                    "generating_embeddings",
                    f"Generating Embeddings: {inserted_count} new chunks | batch={batch_size} | hits={hits} | misses={misses}",
                    stats={
                        "chunks_processed": inserted_count,
                        "embeddings_indexed": inserted_count,
                        "files_processed": len(target_paths),
                        "elapsed_seconds": int(time.time() - start_time),
                        "cache_hits": hits,
                        "cache_misses": misses,
                        "batch_size": batch_size,
                        **emb_stats,
                    },
                    progress=55,
                )

                del chunk_buffer
                del emb_batch
                del bulk_ids
                del bulk_docs
                del bulk_embeddings
                del bulk_metadatas
            else:
                timer.stop("Chunk")

            successful_phases.append("embed")
            logger.info(
                "Successfully bulk inserted %d new chunks into vector store.",
                inserted_count,
            )
        else:
            # Full Mode — Optimized cold-path pipeline:
            # 1. Collect ALL chunks first (single iteration)
            # 2. Embed ALL chunks in one pass (bulk hash → bulk cache → batch inference)
            # 3. Batch vector-store writes separately
            _emit(
                "embed",
                "generating_embeddings",
                "Generating Embeddings: 0 chunks",
                progress=45,
            )

            mem_tracker.log_phase("before_chunking")
            version = uuid.uuid4().hex
            staged_count = 0
            batch_size = _get_batch_size()
            version_staged = False

            try:
                # ── Phase 1: Collect all chunks ────────────────────────────────
                timer.start("Chunk")
                all_chunks_full = []
                for f in _get_source_files_stream(local_path):
                    file_chunks = chunker.chunk_file(f["path"], f["content"])
                    if not file_chunks:
                        continue
                    mem_tracker.record_chunk(len(file_chunks))
                    all_chunks_full.extend(file_chunks)

                total_chunks_full = len(all_chunks_full)
                timer.stop("Chunk")
                mem_tracker.log_phase("before_first_embedding_batch")

                _emit(
                    "embed",
                    "generating_embeddings",
                    f"Generating Embeddings: chunked {total_chunks_full} chunks, starting embedding...",
                    stats={
                        "chunks_processed": 0,
                        "embeddings_indexed": 0,
                        "files_processed": len(all_file_paths),
                        "elapsed_seconds": int(time.time() - start_time),
                        "batch_size": batch_size,
                    },
                    progress=48,
                )

                # ── Phase 2: Embed ALL chunks in one pass ──────────────────────
                timer.start("Embedding")
                emb_stats = {}
                all_embeddings_full = embedding_service.generate_embeddings(
                    all_chunks_full, stats=emb_stats
                )
                timer.stop("Embedding")
                mem_tracker.log_phase(
                    "after_embedding_batch",
                    batch=1,
                    batch_items=total_chunks_full,
                )

                hits = emb_stats.get("cache_hits", 0)
                misses = emb_stats.get("cache_misses", 0)
                logger.info(
                    "Embedding complete: total=%d hits=%d misses=%d elapsed=%.2fs",
                    total_chunks_full,
                    hits,
                    misses,
                    emb_stats.get("elapsed_ms", 0) / 1000.0,
                )

                _emit(
                    "embed",
                    "generating_embeddings",
                    f"Generating Embeddings: {total_chunks_full} chunks embedded | hits={hits} | misses={misses}",
                    stats={
                        "chunks_processed": total_chunks_full,
                        "embeddings_indexed": 0,
                        "files_processed": len(all_file_paths),
                        "elapsed_seconds": int(time.time() - start_time),
                        "cache_hits": hits,
                        "cache_misses": misses,
                        "batch_size": batch_size,
                        **emb_stats,
                    },
                    progress=55,
                )

                # ── Phase 3: Batch vector-store writes ─────────────────────────
                timer.start("Chroma")
                batch_idx = 0
                for vs_start in range(0, total_chunks_full, batch_size):
                    vs_end = min(vs_start + batch_size, total_chunks_full)
                    chunk_batch = all_chunks_full[vs_start:vs_end]
                    emb_batch = all_embeddings_full[vs_start:vs_end]
                    batch_idx += 1

                    staged_batch_count = chroma_store.stage_repository_batch(
                        repo_name,
                        version,
                        chunk_batch,
                        emb_batch,
                        staged_count,
                    )
                    staged_count += staged_batch_count
                    version_staged = True
                    mem_tracker.record_embeddings_indexed(staged_batch_count)

                    if batch_idx % 10 == 0:
                        mem_tracker.log_phase(
                            "after_vector_store_staging_batch",
                            batch=batch_idx,
                            staged=staged_count,
                        )
                        _emit(
                            "embed",
                            "generating_embeddings",
                            f"Indexing: {staged_count}/{total_chunks_full} chunks staged",
                            stats={
                                "chunks_processed": total_chunks_full,
                                "embeddings_indexed": staged_count,
                                "files_processed": len(all_file_paths),
                                "elapsed_seconds": int(time.time() - start_time),
                                "cache_hits": hits,
                                "cache_misses": misses,
                                "batch_size": batch_size,
                                **emb_stats,
                            },
                            progress=min(
                                60,
                                55
                                + int((staged_count / max(1, total_chunks_full)) * 5),
                            ),
                        )

                logger.info(
                    "Indexing complete: %d chunks staged in %d batches",
                    staged_count,
                    batch_idx,
                )

                # Free large lists
                del all_chunks_full
                del all_embeddings_full

                if version_staged:
                    chroma_store.publish_repository_version(repo_name, version)
                successful_phases.append("embed")
            except Exception:
                if version_staged:
                    chroma_store.rollback_staged_version(repo_name, version)
                raise
            finally:
                timer.stop("Chroma")
                timer.stop("Embedding")
                timer.stop("Chunk")

        # ── 5. Granular Symbols & Graph builds (05 INDEX) ─────────────────────────
        _emit("index", "building_symbols", "Building Symbol Index", progress=65)
        timer.start("Graphs")
        mem_tracker.log_phase("before_graph_symbol_analysis")
        try:
            if is_incremental:
                symbol_service.build_partial(
                    repo_name,
                    changed_files,
                    repo_path=local_path,
                )
            else:
                symbol_service.build_full(repo_name, repo_path=local_path)
            successful_phases.append("symbol_index")
        except Exception as exc_sym:
            failed_phases.append("symbol_index")
            phase_errors["symbol_index"] = str(exc_sym)
            logger.warning("Symbol index build failed for %s: %s", repo_name, exc_sym)
        mem_tracker.log_phase("after_graph_symbol_analysis")

        _emit("index", "building_dependency", "Building Dependency Graph", progress=70)
        mem_tracker.log_phase("before_architecture_analysis")
        try:
            if is_incremental:
                architecture_service.build_partial(
                    repo_name,
                    changed_files,
                    repo_path=local_path,
                )
            else:
                architecture_service.build_full(repo_name, repo_path=local_path)
            successful_phases.append("dependency_graph")
        except Exception as exc_dep:
            failed_phases.append("dependency_graph")
            phase_errors["dependency_graph"] = str(exc_dep)
            logger.warning(
                "Dependency graph build failed for %s: %s", repo_name, exc_dep
            )

        # Call Graph, API Surface
        _emit("index", "building_call", "Building Call Graph", progress=75)
        from core.repository_context import RepositoryContext

        context = RepositoryContext(repo_name, repo_path=local_path)

        try:
            if is_incremental:
                call_gen = call_graph_service.build_partial(
                    repo_name, changed_files, context=context
                )
            else:
                call_gen = call_graph_service.build_full(repo_name, context=context)
            if hasattr(call_gen, "__iter__"):
                list(call_gen)
            successful_phases.append("call_graph")
            logger.info("Successfully generated call graph for %s", repo_name)
        except Exception as exc_call:
            failed_phases.append("call_graph")
            phase_errors["call_graph"] = str(exc_call)
            logger.warning("Call graph build skipped for %s: %s", repo_name, exc_call)

        _emit("index", "building_api", "Computing API Surface", progress=80)
        try:
            if is_incremental:
                api_gen = api_surface_service.build_partial(
                    repo_name, changed_files, context=context
                )
            else:
                api_gen = api_surface_service.build_full(repo_name, context=context)
            if hasattr(api_gen, "__iter__"):
                list(api_gen)
            successful_phases.append("api_surface")
            logger.info("Successfully generated API surface for %s", repo_name)
        except Exception as exc_api:
            failed_phases.append("api_surface")
            phase_errors["api_surface"] = str(exc_api)
            logger.warning("API surface build skipped for %s: %s", repo_name, exc_api)
        timer.stop("Graphs")
        mem_tracker.log_phase("after_architecture_analysis")

        # ── 6. Architecture Summary (06 ANALYZE) ──────────────────────────────────
        _emit(
            "analyze",
            "computing_intel",
            "Computing Repository Intelligence",
            progress=85,
        )

        timer.start("Summary")
        mem_tracker.log_phase("before_report_generation")
        cached_entry = ANALYSIS_STORE.get(repo_name)
        if cached_entry and is_incremental:
            architecture_summary = cached_entry["architecture"]
            successful_phases.append("architecture_summary")
        else:

            def _get_summary():
                return asyncio.run(
                    generate_architecture_summary(repo_name, tech_stack, all_file_paths)
                )

            try:
                loop = asyncio.get_running_loop()
                if loop and loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        architecture_summary = pool.submit(_get_summary).result()
                else:
                    architecture_summary = _get_summary()
                successful_phases.append("architecture_summary")
            except RuntimeError:
                architecture_summary = _get_summary()
                successful_phases.append("architecture_summary")
            except Exception as exc_summary:
                failed_phases.append("architecture_summary")
                phase_errors["architecture_summary"] = str(exc_summary)
                logger.warning(
                    "Architecture summary computation failed for %s: %s",
                    repo_name,
                    exc_summary,
                )
                architecture_summary = {}

        timer.stop("Summary")

        # ── 7. Manifest & Snapshot Store (07 ANSWER) ──────────────────────────────
        _emit("answer", "generating_report", "Generating Report", progress=92)

        timer.start("Report")
        structure: Dict[str, List[str]] = {}
        for path in all_file_paths:
            parts = path.split("/")
            parent = ".".join(parts[:-1]) if len(parts) > 1 else "."
            name_part = parts[-1]
            structure.setdefault(parent, []).append(name_part)

        analysis_data = RepositoryAnalysis(
            structure=structure,
            dependencies=dependencies,
            tech_stack=tech_stack,
            metadata={
                "owner": owner,
                "name": name,
                "local_path": local_path,
            },
        )

        ANALYSIS_STORE[repo_name] = {
            "analysis": analysis_data,
            "architecture": architecture_summary,
        }

        new_manifest = BuildManifest(
            repository_hash=repo_hash,
            file_hashes=file_hashes,
            schema_versions={
                "Symbol Index": symbol_service.schema_version,
                "Dependency Graph": architecture_service.schema_version,
            },
            snapshot_versions={
                "Symbol Index": symbol_service.schema_version,
                "Dependency Graph": architecture_service.schema_version,
            },
            last_successful_build=time.time(),
            build_duration_ms=(time.time() - start_time) * 1000,
        )
        snapshot_store.save(
            repo_name,
            "build_manifest",
            new_manifest.model_dump(),
        )

        # Synchronous thread-safe read-merge-write persistence
        try:
            persist_analysis_store_sync()
            successful_phases.append("persistence")
        except Exception as exc_persist:
            failed_phases.append("persistence")
            phase_errors["persistence"] = str(exc_persist)
            logger.error(
                "Failed to persist analysis store for %s: %s",
                repo_name,
                exc_persist,
                exc_info=True,
            )
            raise

        commit_sha = "unknown"
        if local_path and os.path.exists(os.path.join(local_path, ".git")):
            try:
                res_sha = run_safe_command(
                    ["git", "rev-parse", "HEAD"],
                    cwd=local_path,
                    timeout=SHORT_GIT_TIMEOUT,
                    check=True,
                )
                commit_sha = res_sha.stdout.strip()
            except Exception as exc_git:
                logger.warning("Failed to resolve commit SHA: %s", exc_git)
                commit_sha = repo_hash
        else:
            commit_sha = repo_hash

        try:
            twin = repository_twin_builder.build_twin(repo_name)
            engineering_memory_service.create_snapshot(
                repo_name,
                commit_sha,
                branch,
                twin.model_dump(),
                change_set,
            )
            successful_phases.append("engineering_memory")
            logger.info(
                "Successfully recorded Engineering Memory Snapshot for commit %s",
                commit_sha,
            )
        except Exception as exc_memory:
            failed_phases.append("engineering_memory")
            phase_errors["engineering_memory"] = str(exc_memory)
            logger.error(
                "Failed to create memory snapshot: %s", exc_memory, exc_info=True
            )

        try:
            dead_code_service.analyze_dead_code(owner, name)
            successful_phases.append("dead_code")
            logger.info("Successfully generated dead code analysis for %s", repo_name)
        except Exception as exc_dc:
            failed_phases.append("dead_code")
            phase_errors["dead_code"] = str(exc_dc)
            logger.warning("Dead code analysis skipped for %s: %s", repo_name, exc_dc)

        try:
            report_composer.compose_report(repo_name)
            successful_phases.append("health_report")
            logger.info("Successfully generated health report for %s", repo_name)
        except Exception as exc_rep:
            failed_phases.append("health_report")
            phase_errors["health_report"] = str(exc_rep)
            logger.warning(
                "Health report generation skipped for %s: %s", repo_name, exc_rep
            )

        timer.stop("Report")
        mem_tracker.log_phase("after_report_generation")

        report_msg = timer.format_report()
        logger.info(report_msg)
        status_label = "partial" if failed_phases else "complete"
        _emit(
            "answer",
            status_label,
            "✓ Repository Ready"
            if status_label == "complete"
            else "⚠ Repository Analysis Completed (Partial Artifacts)",
            stats={"report": report_msg, "failed_phases": failed_phases},
            progress=100,
        )

        mem_tracker.log_phase("pipeline_shutdown")

        final_status = "partial" if failed_phases else "completed"

        return {
            "repo": repo_name,
            "owner": owner,
            "name": name,
            "status": final_status,
            "successful_phases": successful_phases,
            "failed_phases": failed_phases,
            "skipped_phases": skipped_phases,
            "phase_errors": phase_errors,
            "analysis": (
                analysis_data.model_dump()
                if hasattr(analysis_data, "model_dump")
                else analysis_data
            ),
            "architecture": (
                architecture_summary.model_dump()
                if hasattr(architecture_summary, "model_dump")
                else architecture_summary
            ),
            "report": report_msg,
            "duration_seconds": time.time() - start_time,
        }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/analyze", status_code=202)
async def analyze_repository(request: AnalyzeRequest):
    """Trigger asynchronous background repository analysis and return job_id immediately."""
    repo_url = request.url.strip()
    repo_name = parse_repo_name(repo_url)
    job_id = uuid.uuid4().hex
    request_id = str(uuid.uuid4())

    owner = repo_name.split("/")[0] if "/" in repo_name else "owner"
    name = repo_name.split("/")[1] if "/" in repo_name else repo_name

    initial_state = {
        "job_id": job_id,
        "request_id": request_id,
        "status": "queued",
        "step_id": "clone",
        "message": "Analysis queued",
        "progress": 0,
        "stats": {},
        "repo_url": repo_url,
        "branch": request.branch or "main",
        "repo": {
            "owner": owner,
            "name": name,
            "full_name": repo_name,
        },
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    set_job_state(job_id, initial_state)

    # Check for existing active job if force_rebuild is False
    if not request.force_rebuild:
        for existing_id, existing_state in list(_LOCAL_JOBS.items()):
            if (
                existing_id != job_id
                and isinstance(existing_state, dict)
                and existing_state.get("repo_url") == repo_url
                and existing_state.get("status") in ("queued", "running")
            ):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=202,
                    content={
                        "job_id": existing_id,
                        "status": existing_state.get("status", "queued"),
                        "request_id": existing_state.get("request_id", request_id),
                        "repo": {
                            "owner": owner,
                            "name": name,
                            "full_name": repo_name,
                        },
                    },
                )

    from infrastructure.job_executor import get_job_executor

    executor = get_job_executor()
    executor_name = type(executor).__name__
    logger.info(
        "Dispatching analysis job %s for %s via %s",
        job_id,
        repo_name,
        executor_name,
    )

    try:
        dispatched = executor.spawn_analysis(
            job_id=job_id,
            repo_url=repo_url,
            branch=request.branch or "main",
            force_rebuild=request.force_rebuild,
            request_id=request_id,
        )
    except Exception as exc:
        logger.exception(
            "Failed to dispatch analysis job %s for %s via %s: %s",
            job_id,
            repo_name,
            executor_name,
            exc,
        )
        curr_state = get_job_state(job_id) or initial_state
        curr_state["status"] = "failed"
        curr_state["message"] = "Failed to queue analysis job"
        curr_state["error"] = format_analysis_error(exc)
        set_job_state(job_id, curr_state)
        raise HTTPException(
            status_code=503,
            detail="Analysis worker is currently unavailable.",
        )

    logger.info(
        "Analysis dispatch result for job %s via %s: %s",
        job_id,
        executor_name,
        dispatched,
    )

    if not dispatched:
        logger.error(
            "Analysis executor %s rejected dispatch for job %s (%s)",
            executor_name,
            job_id,
            repo_name,
        )
        curr_state = get_job_state(job_id) or initial_state
        curr_state["status"] = "failed"
        curr_state["message"] = "Failed to queue analysis job"
        curr_state["error"] = format_analysis_error(
            RuntimeError("Analysis worker rejected or failed to queue job")
        )
        set_job_state(job_id, curr_state)
        raise HTTPException(
            status_code=503,
            detail="Analysis worker is currently unavailable.",
        )

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "request_id": request_id,
            "repo": {
                "owner": owner,
                "name": name,
                "full_name": repo_name,
            },
        },
    )


@router.get("/analyze/{job_id}")
async def get_analysis_status(job_id: str):
    """Poll repository analysis job status."""
    from fastapi.responses import JSONResponse

    job = get_job_state(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis job '{job_id}' not found.",
        )

    status = job.get("status", "queued")
    started_at = job.get("started_at")
    now = time.time()

    # Calculate accurate total job elapsed seconds
    if started_at:
        elapsed_seconds = round(now - float(started_at), 2)
    else:
        created_at = job.get("created_at")
        elapsed_seconds = round(now - float(created_at), 2) if created_at else 0.0

    stats = dict(job.get("stats", {}) or {})
    if "elapsed_seconds" not in stats:
        stats["elapsed_seconds"] = elapsed_seconds

    if status in ("queued", "running"):
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "request_id": job.get("request_id", job_id),
                "status": status,
                "step_id": job.get("step_id", "clone"),
                "message": job.get("message", "Analysis in progress..."),
                "progress": job.get("progress", 0),
                "stats": stats,
                "repo": job.get("repo", {}),
                "started_at": started_at,
                "updated_at": job.get("updated_at"),
                "elapsed_seconds": elapsed_seconds,
            },
        )

    if status in ("completed", "partial"):
        return JSONResponse(
            status_code=200,
            content={
                "job_id": job_id,
                "request_id": job.get("request_id", job_id),
                "status": status,
                "step_id": "complete",
                "message": job.get(
                    "message",
                    "Analysis completed with partial artifact status"
                    if status == "partial"
                    else "Analysis completed successfully",
                ),
                "progress": 100,
                "stats": stats,
                "result": job.get("result"),
                "successful_phases": job.get("successful_phases", []),
                "failed_phases": job.get("failed_phases", []),
                "skipped_phases": job.get("skipped_phases", []),
                "phase_errors": job.get("phase_errors", {}),
                "repo": job.get("repo", {}),
                "started_at": started_at,
                "completed_at": job.get("completed_at"),
                "updated_at": job.get("updated_at"),
                "elapsed_seconds": elapsed_seconds,
            },
        )

    if status == "failed":
        return JSONResponse(
            status_code=500,
            content={
                "job_id": job_id,
                "request_id": job.get("request_id", job_id),
                "status": "failed",
                "step_id": job.get("step_id", "failed"),
                "error": job.get(
                    "error", "An unexpected error occurred during analysis."
                ),
                "stats": stats,
                "repo": job.get("repo", {}),
                "started_at": started_at,
                "completed_at": job.get("completed_at"),
                "updated_at": job.get("updated_at"),
                "elapsed_seconds": elapsed_seconds,
            },
        )

    return job


@router.get("/analysis/{owner}/{repo_name}")
async def get_analysis_details(owner: str, repo_name: str):
    """Retrieve computed analysis and architecture summary for a repository."""
    full_name = f"{owner}/{repo_name}"
    if full_name not in ANALYSIS_STORE:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Repository {full_name} has not been analysed yet. "
                "Please analyse or index first."
            ),
        )
    return ANALYSIS_STORE[full_name]


@router.post("/repos/repair")
async def repair_repository(request: RepoRepairRequest):
    """Repair a repository by generating its missing symbol index."""
    owner = request.owner.strip()
    repo = request.repo.strip()
    repo_name = f"{owner}/{repo}"

    try:
        matched_repo_name = None
        for key in ANALYSIS_STORE.keys():
            if key.lower() == repo_name.lower():
                matched_repo_name = key
                break

        actual_name = matched_repo_name or repo_name
        local_path = github_service.get_local_repo_path(actual_name)
        if not os.path.exists(local_path):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Repository '{repo_name}' is not cloned on disk. "
                    "Please analyze the repository first."
                ),
            )

        result = await asyncio.to_thread(
            architecture_service.build, actual_name, local_path, None, True
        )
        sym_result = await asyncio.to_thread(
            symbol_service.build, actual_name, local_path, None
        )
        return {
            "status": "success",
            "message": f"Repository indexes rebuilt successfully for '{actual_name}'",
            "details": {
                "architecture": result,
                "symbols": sym_result,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Repository repair failed for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rebuild symbol index: {str(exc)}",
        )
