"""API Surface Intelligence router.

Endpoints:
  POST /api/api-surface/build                                 (SSE stream)
  GET  /api/api-surface/{owner}/{repo_name}
  GET  /api/api-surface/{owner}/{repo_name}/stats
  GET  /api/api-surface/{owner}/{repo_name}/public
  GET  /api/api-surface/{owner}/{repo_name}/internal
  GET  /api/api-surface/{owner}/{repo_name}/deprecated
  GET  /api/api-surface/{owner}/{repo_name}/breaking
  GET  /api/api-surface/{owner}/{repo_name}/{symbol_name}
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import os

from backend.dependencies import (
    ANALYSIS_STORE,
    get_api_surface_service,
    get_breaking_change_analyzer,
    get_github_service,
    get_symbol_service,
    get_snapshot_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-surface", tags=["API Surface"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class APISurfaceBuildRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _advance_generator(gen):
    """Advance a generator by one step in a thread pool worker, safely capturing completion."""
    try:
        return False, next(gen)
    except StopIteration as stop:
        return True, stop.value


@router.post("/build")
async def build_api_surface(request: APISurfaceBuildRequest):
    """Build the API surface index for a repository. Streams SSE progress."""
    repo_name = request.repo.strip()
    if not repo_name:
        raise HTTPException(status_code=422, detail="repo must not be empty.")

    if repo_name not in ANALYSIS_STORE:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' not found. Run POST /api/analyze first.",
        )
    if not get_symbol_service().index_exists(repo_name):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No symbol index for '{repo_name}'. Run POST /api/v1/analyze first."
            ),
        )

    async def event_generator():
        try:
            local_path = (
                ANALYSIS_STORE[repo_name]["analysis"].metadata.get("local_path", "")
                if repo_name in ANALYSIS_STORE
                else ""
            )
            files = []
            if local_path and os.path.exists(local_path):
                files = await asyncio.to_thread(
                    get_github_service().extract_source_files, local_path
                )
            if not files:
                parsed_data = get_snapshot_store().load(repo_name, "parsed_files")
                if parsed_data and "parsed" in parsed_data:
                    files = [
                        {
                            "path": p.get("file_path", ""),
                            "content": p.get("content", ""),
                        }
                        for p in parsed_data["parsed"]
                        if p.get("content")
                    ]
            if not files:
                try:
                    cloned_path = await asyncio.to_thread(
                        get_github_service().clone_repo,
                        f"https://github.com/{repo_name}.git",
                    )
                    files = await asyncio.to_thread(
                        get_github_service().extract_source_files, cloned_path
                    )
                except Exception as exc_clone:
                    logger.warning(
                        "Clone fallback failed for %s: %s", repo_name, exc_clone
                    )

            gen = get_api_surface_service().build(repo_name, files)
            surface = None
            while True:
                is_done, value = await asyncio.to_thread(_advance_generator, gen)
                if is_done:
                    surface = value
                    break
                yield f"data: {json.dumps(value)}\n\n"

            if surface is not None:
                yield f"data: {json.dumps({'status': 'result', 'data': surface.stats.model_dump()})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"

        except (ValueError, HTTPException) as ve:
            yield f"data: {json.dumps({'status': 'error', 'message': str(ve)})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"
        except Exception as exc:
            logger.error(
                "API surface build SSE error for %s: %s",
                repo_name,
                exc,
                exc_info=True,
            )
            yield f"data: {json.dumps({'status': 'error', 'message': str(exc)})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{owner}/{repo_name}")
async def get_api_surface(owner: str, repo_name: str):
    """Return the full API surface report."""
    full_name = f"{owner}/{repo_name}"
    surface = await asyncio.to_thread(get_api_surface_service().load, full_name)
    if surface is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No API surface data for '{full_name}'. "
                "Please analyze the repository first."
            ),
        )
    return surface.model_dump()


@router.get("/{owner}/{repo_name}/stats")
async def get_api_surface_stats(owner: str, repo_name: str):
    """Return aggregate statistics for the API surface."""
    full_name = f"{owner}/{repo_name}"
    stats = await asyncio.to_thread(get_api_surface_service().get_stats, full_name)
    if stats is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No API surface data for '{full_name}'. "
                "Please analyze the repository first."
            ),
        )
    return stats.model_dump()


@router.get("/{owner}/{repo_name}/public")
async def get_public_api(
    owner: str,
    repo_name: str,
    q: Optional[str] = Query(None, description="Search query"),
    kind: Optional[str] = Query(None, description="Filter by api_kind value"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Return all public symbols."""
    full_name = f"{owner}/{repo_name}"
    if q:
        results = await asyncio.to_thread(
            get_api_surface_service().search, full_name, q, "public", kind, limit
        )
    else:
        symbols = await asyncio.to_thread(
            get_api_surface_service().get_public, full_name
        )
        if kind:
            symbols = [s for s in symbols if s.api_kind.value == kind]
        results = symbols[:limit]

    if not results and not await asyncio.to_thread(
        get_api_surface_service().surface_exists, full_name
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No API surface data for '{full_name}'. "
                "Run POST /api/api-surface/build first."
            ),
        )
    return {"symbols": [s.model_dump() for s in results], "count": len(results)}


@router.get("/{owner}/{repo_name}/internal")
async def get_internal_api(
    owner: str,
    repo_name: str,
    limit: int = Query(100, ge=1, le=1000),
):
    """Return all internal symbols."""
    full_name = f"{owner}/{repo_name}"
    symbols = await asyncio.to_thread(get_api_surface_service().get_internal, full_name)
    if not symbols and not await asyncio.to_thread(
        get_api_surface_service().surface_exists, full_name
    ):
        raise HTTPException(
            status_code=404,
            detail=f"No API surface data for '{full_name}'.",
        )
    return {
        "symbols": [s.model_dump() for s in symbols[:limit]],
        "count": len(symbols),
    }


@router.get("/{owner}/{repo_name}/deprecated")
async def get_deprecated_api(owner: str, repo_name: str):
    """Return all deprecated symbols."""
    full_name = f"{owner}/{repo_name}"
    symbols = await asyncio.to_thread(
        get_api_surface_service().get_deprecated, full_name
    )
    if not symbols and not await asyncio.to_thread(
        get_api_surface_service().surface_exists, full_name
    ):
        raise HTTPException(
            status_code=404,
            detail=f"No API surface data for '{full_name}'.",
        )
    return {"symbols": [s.model_dump() for s in symbols], "count": len(symbols)}


@router.get("/{owner}/{repo_name}/breaking")
async def get_breaking_changes(
    owner: str,
    repo_name: str,
    compare_repo: Optional[str] = Query(
        None,
        description=(
            "Compare against this repo's surface (owner/repo). "
            "Omit to get orphaned public APIs instead."
        ),
    ),
):
    """Detect breaking changes between two API surfaces, or return orphaned public APIs."""
    full_name = f"{owner}/{repo_name}"

    if compare_repo:
        before = await asyncio.to_thread(get_api_surface_service().load, compare_repo)
        after = await asyncio.to_thread(get_api_surface_service().load, full_name)
        if before is None:
            raise HTTPException(
                status_code=404,
                detail=f"No API surface data for baseline '{compare_repo}'.",
            )
        if after is None:
            raise HTTPException(
                status_code=404,
                detail=f"No API surface data for '{full_name}'.",
            )
        changes = get_breaking_change_analyzer().diff(before, after)
        return {
            "breaking_changes": [c.model_dump() for c in changes],
            "count": len(changes),
        }

    orphans = await asyncio.to_thread(get_api_surface_service().get_orphans, full_name)
    if not orphans and not await asyncio.to_thread(
        get_api_surface_service().surface_exists, full_name
    ):
        raise HTTPException(
            status_code=404,
            detail=f"No API surface data for '{full_name}'.",
        )
    return {"orphans": [s.model_dump() for s in orphans], "count": len(orphans)}


@router.get("/{owner}/{repo_name}/{symbol_name}")
async def get_api_symbol(owner: str, repo_name: str, symbol_name: str):
    """Return classification details for a single symbol by name."""
    full_name = f"{owner}/{repo_name}"
    symbol = await asyncio.to_thread(
        get_api_surface_service().get_symbol, full_name, symbol_name
    )
    if symbol is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Symbol '{symbol_name}' not found in API surface for '{full_name}'. "
                "Run POST /api/api-surface/build first, or check the symbol name."
            ),
        )
    return symbol.model_dump()
