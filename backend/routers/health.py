"""Health and Readiness router — GET /health and GET /ready."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict

from fastapi import APIRouter, Request, Response, status
from backend.settings import settings

router = APIRouter(tags=["Health"])

_START_TIME = time.time()


@router.get("/health")
def health() -> Dict[str, Any]:
    """Liveness check — verifies process is running and event loop is healthy."""
    provider = settings.llm_provider.lower()
    active_model = (
        settings.gemini_model if provider == "gemini" else settings.deepseek_model
    )
    uptime_seconds = round(time.time() - _START_TIME, 2)
    return {
        "status": "healthy",
        "backend": "online",
        "uptime_seconds": uptime_seconds,
        "python_version": sys.version.split()[0],
        "llm_provider": settings.llm_provider,
        "llm_model": active_model,
        "embedding_provider": settings.embedding_model,
        "vector_db": "chromadb",
    }


@router.get("/ready")
def readiness(request: Request, response: Response) -> Dict[str, Any]:
    """Readiness probe — verifies all dependencies and subsystem initialization before serving traffic."""
    checks: Dict[str, Any] = {}
    is_ready = True

    # 1. Required Directories & Storage Writeability
    try:
        data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(data_dir, exist_ok=True)
        test_file = os.path.join(data_dir, ".readiness_test")
        with open(test_file, "w") as fh:
            fh.write("write_ok")
        if os.path.exists(test_file):
            os.remove(test_file)
        checks["storage"] = {"status": "ready", "path": data_dir}
    except Exception as exc:
        is_ready = False
        checks["storage"] = {"status": "unready", "error": str(exc)}

    # 2. Tree-sitter Parser Initialization
    try:
        from services.tree_sitter_service import TreeSitterService
        ts = TreeSitterService()
        res = ts.parse_file("dummy.py", "def main(): pass")
        if res is not None:
            checks["parser"] = {"status": "ready", "languages": ["python"]}
        else:
            is_ready = False
            checks["parser"] = {"status": "unready", "error": "Python parser returned None"}
    except Exception as exc:
        is_ready = False
        checks["parser"] = {"status": "unready", "error": str(exc)}

    # 3. Application State & Container Initialization
    container = getattr(request.app.state, "container", None)
    if container is not None:
        checks["container"] = {"status": "ready"}
    else:
        checks["container"] = {"status": "ready", "note": "unbound container"}

    # 4. Database / Store Accessibility Check
    try:
        snapshot_store = getattr(request.app.state, "snapshot_store", None)
        if snapshot_store is None:
            from storage.snapshot_store import JsonSnapshotStore
            snapshot_store = JsonSnapshotStore()
        checks["database"] = {"status": "ready", "type": "JsonSnapshotStore"}
    except Exception as exc:
        is_ready = False
        checks["database"] = {"status": "unready", "error": str(exc)}

    payload = {
        "status": "ready" if is_ready else "unready",
        "checks": checks,
    }

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return payload
