"""PR router — Pull Request Intelligence, Architecture Drift, Dead Code (PH2-003/004/005).

Endpoints:
  POST /api/pr/analyze
  GET  /api/pr/health
  POST /api/architecture/drift
  POST /api/dead-code/analyze

Note on service resolution
--------------------------
Each endpoint resolves its service singletons through ``backend.api`` at call
time (``import backend.api as _api`` inside the function body).  This is the
standard Python mock pattern: ``@patch("backend.api.<name>")`` replaces the
attribute on the ``backend.api`` module object, so any code that looks up the
name on that module at call time will see the mock.  Binding the name at import
time (``from backend.dependencies import pr_intelligence_service``) would
capture the original object before the patch fires, making the mock invisible.
"""

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.dependencies import ANALYSIS_STORE
from models import PRAnalyzeRequest, PRDriftRequest, DeadCodeRequest
from services.github_service import GitHubConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["PR Intelligence"])


@router.post("/pr/analyze")
async def analyze_pull_request(request: PRAnalyzeRequest):
    """Analyze a GitHub Pull Request for risk, size, blast radius, symbol diffs, etc."""
    owner = request.owner
    repo = request.repo
    pr_number = request.pr_number

    if not owner or not repo or not pr_number:
        raise HTTPException(
            status_code=422,
            detail=(
                "Must provide either a valid pr_url or all of "
                "owner, repo, and pr_number."
            ),
        )

    repo_name = f"{owner}/{repo}"
    try:
        import backend.api as _api  # late import — test patches backend.api.<name>

        result = await asyncio.to_thread(
            _api.pr_intelligence_service.analyze_pull_request, owner, repo, pr_number
        )
        return result
    except ValueError as val_err:
        logger.warning("PR analysis lookup failed for %s: %s", repo_name, val_err)
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "PR analysis failed for %s (PR #%s): %s",
            repo_name,
            pr_number,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API or analysis pipeline failed: {str(exc)}",
        )


@router.get("/pr/health")
async def get_pr_health(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
):
    """Fast diagnostics endpoint for PR Intelligence."""
    import backend.api as _api  # late import — test patches backend.api.<name>

    token = GitHubConfig.load_token()
    github_token_exists = bool(token)

    rate_info: dict = {"limit": 0, "remaining": 0, "reset": 0}
    try:
        # Synchronous call so @patch("backend.api.github_service") intercepts it
        rate_info = await asyncio.to_thread(_api.github_service.get_rate_limit_info)
    except Exception:
        pass
    github_rate_limit_authenticated = (
        github_token_exists and rate_info.get("limit", 0) >= 5000
    )

    analysis_exists = False
    graph_avail = False
    symbol_avail = False

    if owner and repo:
        repo_name = f"{owner}/{repo}"
        logger.info("[DIAGNOSTICS] Requested repo_name: %s", repo_name)
        logger.info(
            "[DIAGNOSTICS] ANALYSIS_STORE keys: %s", list(ANALYSIS_STORE.keys())
        )

        g_dir = os.path.join("data", "graphs")
        s_dir = os.path.join("data", "symbols")
        if os.path.exists(g_dir):
            logger.info("[DIAGNOSTICS] Graphs files: %s", os.listdir(g_dir))
        if os.path.exists(s_dir):
            logger.info("[DIAGNOSTICS] Symbols files: %s", os.listdir(s_dir))

        analysis_exists = any(
            k.lower() == repo_name.lower() for k in ANALYSIS_STORE.keys()
        )
        try:
            # Synchronous calls so @patch("backend.api.<service>") intercepts them
            graph_avail = _api.graph_service.graph_exists(repo_name)
            symbol_avail = _api.symbol_service.index_exists(repo_name)
        except Exception:
            pass

    return {
        "github_token": github_token_exists,
        "github_auth": github_token_exists,
        "github_token_loaded": github_token_exists,
        # Credential material is never returned to clients; only presence is reported.
        "github_token_prefix": "configured" if token else "missing",
        "github_rate_limit_authenticated": github_rate_limit_authenticated,
        "rate_limit_remaining": rate_info.get("remaining", 0),
        "analysis_exists": analysis_exists,
        "graph_available": graph_avail,
        "symbol_index_available": symbol_avail,
        "status": "healthy",
    }


@router.post("/architecture/drift")
async def analyze_architecture_drift(request: PRDriftRequest):
    """Analyze a GitHub Pull Request for architectural drift, cycle changes, and coupling."""
    owner = request.owner
    repo = request.repo
    pr_number = request.pr_number

    if not owner or not repo or not pr_number:
        raise HTTPException(
            status_code=422,
            detail=(
                "Must provide either a valid pr_url or all of "
                "owner, repo, and pr_number."
            ),
        )

    repo_name = f"{owner}/{repo}"
    try:
        import backend.api as _api  # late import — test patches backend.api.<name>

        result = await asyncio.to_thread(
            _api.architecture_drift_service.analyze_drift, owner, repo, pr_number
        )
        return result
    except ValueError as val_err:
        logger.warning("Drift analysis lookup failed for %s: %s", repo_name, val_err)
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Drift analysis failed for %s (PR #%s): %s",
            repo_name,
            pr_number,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API or drift analysis pipeline failed: {str(exc)}",
        )


@router.post("/dead-code/analyze")
async def analyze_dead_code(request: DeadCodeRequest):
    """Analyze a repository for dead code, orphan modules, and dead dependency chains."""
    owner = request.owner
    repo = request.repo
    repo_name = f"{owner}/{repo}"
    try:
        import backend.api as _api  # late import — test patches backend.api.<name>

        result = await asyncio.to_thread(
            _api.dead_code_service.analyze_dead_code, owner, repo
        )
        return result
    except ValueError as val_err:
        logger.warning(
            "Dead code analysis lookup failed for %s: %s", repo_name, val_err
        )
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Dead code analysis failed for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=502,
            detail=f"Dead code analysis pipeline failed: {str(exc)}",
        )
