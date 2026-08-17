"""Call Graph router — Function Call Graph Intelligence.

Endpoints:
  POST /api/call-graph/build                                  (SSE stream)
  GET  /api/call-graph/{owner}/{repo_name}
  GET  /api/call-graph/{owner}/{repo_name}/stats
  GET  /api/call-graph/{owner}/{repo_name}/callers/{fn}
  GET  /api/call-graph/{owner}/{repo_name}/callees/{fn}
  GET  /api/call-graph/{owner}/{repo_name}/hierarchy/{fn}
  GET  /api/call-graph/{owner}/{repo_name}/blast-radius/{fn}
  GET  /api/call-graph/{owner}/{repo_name}/neighbors/{fn}
  GET  /api/call-graph/{owner}/{repo_name}/trace/{fn}
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.dependencies import (
    ANALYSIS_STORE,
    call_graph_service,
    github_service,
    symbol_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/call-graph", tags=["Call Graph"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CallGraphBuildRequest(BaseModel):
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
async def build_call_graph(request: CallGraphBuildRequest):
    """Build the function call graph. Streams SSE progress."""
    repo_name = request.repo.strip()
    if not repo_name:
        raise HTTPException(status_code=422, detail="repo must not be empty.")

    if repo_name not in ANALYSIS_STORE:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' not found. Run POST /api/analyze first.",
        )
    if not symbol_service.index_exists(repo_name):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No symbol index for '{repo_name}'. "
                "Run POST /api/architecture/build first."
            ),
        )

    async def event_generator():
        try:
            local_path = ANALYSIS_STORE[repo_name]["analysis"].metadata.get(
                "local_path", ""
            )
            files = await asyncio.to_thread(
                github_service.extract_source_files, local_path
            )

            gen = call_graph_service.build(repo_name, files)
            summary = None
            while True:
                is_done, value = await asyncio.to_thread(_advance_generator, gen)
                if is_done:
                    summary = value
                    break
                yield f"data: {json.dumps(value)}\n\n"

            if summary is not None:
                yield f"data: {json.dumps({'status': 'result', 'data': summary.model_dump()})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"

        except (ValueError, HTTPException) as ve:
            yield f"data: {json.dumps({'status': 'error', 'message': str(ve)})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"
        except Exception as exc:
            logger.error(
                "Call graph build SSE error for %s: %s", repo_name, exc, exc_info=True
            )
            yield f"data: {json.dumps({'status': 'error', 'message': str(exc)})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{owner}/{repo_name}")
async def get_call_graph(
    owner: str,
    repo_name: str,
    q: Optional[str] = Query(None, description="Search query to filter functions"),
    max_nodes: int = Query(300, ge=1, le=1000),
):
    """Return the call graph as React Flow JSON."""
    full_name = f"{owner}/{repo_name}"
    result = await asyncio.to_thread(
        call_graph_service.get_graph_json, full_name, q, max_nodes
    )
    if result.get("error") and result.get("node_count", 0) == 0:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{owner}/{repo_name}/stats")
async def get_call_graph_stats(owner: str, repo_name: str):
    """Return call graph aggregate statistics."""
    full_name = f"{owner}/{repo_name}"
    stats = await asyncio.to_thread(call_graph_service.get_stats, full_name)
    if "error" in stats:
        raise HTTPException(status_code=404, detail=stats["error"])
    return stats


@router.get("/{owner}/{repo_name}/callers/{function_id:path}")
async def get_callers(owner: str, repo_name: str, function_id: str):
    """Return all functions that directly call the given function."""
    full_name = f"{owner}/{repo_name}"
    G = await asyncio.to_thread(call_graph_service.load_graph, full_name)
    if G is None:
        raise HTTPException(
            status_code=404,
            detail=f"Call graph not found for '{full_name}'.",
        )
    callers = await asyncio.to_thread(
        call_graph_service.get_callers, full_name, function_id
    )
    return {"function_id": function_id, "callers": [c.model_dump() for c in callers]}


@router.get("/{owner}/{repo_name}/callees/{function_id:path}")
async def get_callees(owner: str, repo_name: str, function_id: str):
    """Return all functions directly called by the given function."""
    full_name = f"{owner}/{repo_name}"
    G = await asyncio.to_thread(call_graph_service.load_graph, full_name)
    if G is None:
        raise HTTPException(
            status_code=404,
            detail=f"Call graph not found for '{full_name}'.",
        )
    callees = await asyncio.to_thread(
        call_graph_service.get_callees, full_name, function_id
    )
    return {"function_id": function_id, "callees": [c.model_dump() for c in callees]}


@router.get("/{owner}/{repo_name}/hierarchy/{function_id:path}")
async def get_call_hierarchy(
    owner: str,
    repo_name: str,
    function_id: str,
    direction: str = Query("down", description="'down' (callees) or 'up' (callers)"),
    depth: int = Query(6, ge=1, le=12),
):
    """Return the call hierarchy tree for a function."""
    full_name = f"{owner}/{repo_name}"
    tree = await asyncio.to_thread(
        call_graph_service.get_hierarchy, full_name, function_id, direction, depth
    )
    if tree is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Function '{function_id}' not found in call graph for '{full_name}'."
            ),
        )
    return tree.model_dump()


@router.get("/{owner}/{repo_name}/blast-radius/{function_id:path}")
async def get_function_blast_radius(owner: str, repo_name: str, function_id: str):
    """Return the function-level blast radius for the given function."""
    full_name = f"{owner}/{repo_name}"
    result = await asyncio.to_thread(
        call_graph_service.get_blast_radius, full_name, function_id
    )
    return result.model_dump()


@router.get("/{owner}/{repo_name}/neighbors/{function_id:path}")
async def get_call_graph_neighbors(owner: str, repo_name: str, function_id: str):
    """Return immediate callers + callees as React Flow JSON."""
    full_name = f"{owner}/{repo_name}"
    result = await asyncio.to_thread(
        call_graph_service.get_neighbors_json, full_name, function_id
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{owner}/{repo_name}/trace/{function_id:path}")
async def get_call_graph_trace(
    owner: str,
    repo_name: str,
    function_id: str,
    direction: str = Query("both", description="forward | backward | both"),
    depth: int = Query(6, ge=1, le=12),
):
    """Return a BFS trace from a function as React Flow JSON."""
    full_name = f"{owner}/{repo_name}"
    result = await asyncio.to_thread(
        call_graph_service.get_trace_json, full_name, function_id, direction, depth
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result
