"""Modal entrypoint for ARIA (AI-Powered Repository Intelligence Agent).

Deploys the existing FastAPI backend and Astro frontend as a unified serverless ASGI application,
with a dedicated long-running background Modal Function for asynchronous repository analysis.

Features:
  - Preserves 100% of existing API routes (/api/v1/*, /health, /metrics, /docs)
  - Dedicated background Modal Function run_analysis_job (up to 3600s timeout)
  - Distributed job progress tracking via modal.Dict ("aria-analysis-jobs")
  - Preserves existing Astro static frontend serving directly from FastAPI
  - Connects to external Qdrant Cloud vector database
  - Offloads LLM inference to Gemini / DeepSeek APIs
  - Uses Modal Volume for persistent SQLite relational metadata and analysis store
  - Serverless auto-scaling with scale-to-zero cost efficiency and warm scaledown window
"""

import os
import sys
import time
import logging

# pyrefly: ignore [missing-import]
import modal

# Ensure project root is in sys.path for local resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Modal Application Definition
# ---------------------------------------------------------------------------
app = modal.App("aria")

# ---------------------------------------------------------------------------
# Container Image Definition
# Reuses the production multi-stage Dockerfile which builds both the Astro
# frontend and backend dependencies.
# ---------------------------------------------------------------------------
image = modal.Image.from_dockerfile("Dockerfile").add_local_python_source(
    "backend", "services", "models", "core", "storage", "utils"
)

# ---------------------------------------------------------------------------
# Persistent Storage (Modal Volume)
# Preserves SQLite database (data/repo_understanding.db) and serialized
# analysis store (data/analysis_store.json) across ephemeral container lifecycles.
# ---------------------------------------------------------------------------
data_volume = modal.Volume.from_name("aria-data", create_if_missing=True)

# ---------------------------------------------------------------------------
# Distributed Job State (Modal Dict)
# Tracks asynchronous analysis progress across independent Modal containers.
# ---------------------------------------------------------------------------
job_progress = modal.Dict.from_name("aria-analysis-jobs", create_if_missing=True)


# ---------------------------------------------------------------------------
# Background Analysis Function
# Executes long repository analysis (clone, parse, embed, index, analyze, answer)
# with a 3600-second timeout outside the HTTP request lifecycle.
# ---------------------------------------------------------------------------
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("aria-secret", required_keys=[]),
    ],
    volumes={
        "/app/data": data_volume,
    },
    cpu=2.0,  # 2 vCPUs for AST parsing & embeddings
    memory=4096,  # 4 GB RAM (BGE embeddings + Tree-sitter + FastAPI)
    timeout=3600,  # 1 hour timeout for background repository analysis
)
def run_analysis_job(
    repo_url: str,
    branch: str = "main",
    force_rebuild: bool = False,
    request_id: str = None,
    job_id: str = None,
):
    """Execute the complete repository analysis pipeline in the background."""
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")

    os.environ.setdefault("SQLITE_DB_PATH", "/tmp/repo_understanding.db")
    os.environ.setdefault("CLONED_REPOS_PATH", "/tmp/cloned_repos")
    os.environ.setdefault("VECTOR_STORE_BACKEND", "qdrant")

    from backend.routers.repositories import (
        execute_repository_analysis,
        format_analysis_error,
        parse_repo_name,
    )

    logger = logging.getLogger("backend.routers.repositories")
    logger.info(
        "Starting background analysis job=%s repo_url=%s request_id=%s",
        job_id,
        repo_url,
        request_id,
    )

    repo_name = parse_repo_name(repo_url)
    owner = repo_name.split("/")[0] if "/" in repo_name else "owner"
    name = repo_name.split("/")[1] if "/" in repo_name else repo_name

    def progress_callback(update_dict):
        try:
            current = job_progress.get(job_id, {})
            current.update(update_dict)
            current["status"] = "running"
            current["updated_at"] = time.time()
            job_progress[job_id] = current
        except Exception as exc:
            logger.warning(
                "Failed to update modal job progress for job=%s: %s", job_id, exc
            )

    try:
        job_progress[job_id] = {
            "job_id": job_id,
            "request_id": request_id,
            "status": "running",
            "step_id": "clone",
            "message": "Starting analysis...",
            "progress": 0,
            "stats": {},
            "repo_url": repo_url,
            "branch": branch,
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

        worker_start_time = time.time()
        initial_created = job_progress.get(job_id, {}).get(
            "created_at", worker_start_time
        )
        queue_time_seconds = round(worker_start_time - initial_created, 2)

        result = execute_repository_analysis(
            repo_url=repo_url,
            branch=branch,
            force_rebuild=force_rebuild,
            progress_callback=progress_callback,
            request_id=request_id,
        )

        compute_elapsed = round(time.time() - worker_start_time, 2)

        # Commit data volume so all snapshots, graphs, and database files are persisted
        commit_start = time.time()
        try:
            data_volume.commit()
            logger.info("Committed modal data_volume after analysis for %s", repo_name)
        except Exception as exc_vol:
            logger.warning("Failed to commit data_volume: %s", exc_vol)
        commit_elapsed = round(time.time() - commit_start, 2)

        now_time = time.time()
        total_wall_clock = round(now_time - initial_created, 2)

        job_progress[job_id] = {
            "job_id": job_id,
            "request_id": request_id,
            "status": "completed",
            "step_id": "answer",
            "message": "Repository analysis completed successfully",
            "progress": 100,
            "stats": {
                "queue_time_seconds": queue_time_seconds,
                "worker_compute_seconds": compute_elapsed,
                "volume_commit_seconds": commit_elapsed,
                "wall_clock_job_duration_seconds": total_wall_clock,
            },
            "repo_url": repo_url,
            "branch": branch,
            "repo": {
                "owner": owner,
                "name": name,
                "full_name": repo_name,
            },
            "result": result,
            "error": None,
            "created_at": initial_created,
            "updated_at": now_time,
        }
        logger.info(
            "Successfully completed background analysis job=%s repo=%s (compute=%.2fs commit=%.2fs total=%.2fs)",
            job_id,
            repo_name,
            compute_elapsed,
            commit_elapsed,
            total_wall_clock,
        )
        return result

    except Exception as exc:
        logger.error(
            "Background analysis failed for job=%s repo=%s: %s",
            job_id,
            repo_name,
            exc,
            exc_info=True,
        )
        safe_error = format_analysis_error(exc)
        job_progress[job_id] = {
            "job_id": job_id,
            "request_id": request_id,
            "status": "failed",
            "step_id": "error",
            "message": "Analysis failed",
            "progress": 0,
            "stats": {},
            "repo_url": repo_url,
            "branch": branch,
            "repo": {
                "owner": owner,
                "name": name,
                "full_name": repo_name,
            },
            "result": None,
            "error": safe_error,
            "updated_at": time.time(),
        }
        raise


# ---------------------------------------------------------------------------
# ASGI Web Application Function
# Exposes the existing FastAPI application instance directly via @modal.asgi_app().
# ---------------------------------------------------------------------------
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("aria-secret", required_keys=[]),
    ],
    volumes={
        "/app/data": data_volume,
    },
    cpu=2.0,  # 2 vCPUs for AST parsing & embeddings
    memory=4096,  # 4 GB RAM (BGE embeddings + Tree-sitter + FastAPI)
    timeout=600,  # 10 minute request timeout for HTTP endpoints
    scaledown_window=300,  # Keep container warm for 5 minutes after traffic
)
@modal.asgi_app()
def serve_aria():
    """Mount and return the existing ARIA FastAPI application."""
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")

    os.environ.setdefault("SQLITE_DB_PATH", "/tmp/repo_understanding.db")
    os.environ.setdefault("CLONED_REPOS_PATH", "/tmp/cloned_repos")
    os.environ.setdefault("VECTOR_STORE_BACKEND", "qdrant")

    # Initial reload to sync any external commits
    try:
        data_volume.reload()
    except Exception:
        pass

    from backend.api import app as existing_fastapi_app

    @existing_fastapi_app.middleware("http")
    async def volume_sync_middleware(request, call_next):
        if request.url.path.startswith("/api/"):
            try:
                data_volume.reload()
            except Exception:
                pass
        return await call_next(request)

    return existing_fastapi_app
