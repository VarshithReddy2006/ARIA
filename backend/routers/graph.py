"""Graph router — Interactive Dependency Graph (PH2-001).

Endpoints:
  GET /api/graph/{owner}/{repo}/full
  GET /api/graph/{owner}/{repo}/neighbors/{node_path}
  GET /api/graph/{owner}/{repo}/trace/{node_path}
  GET /api/graph/{owner}/{repo}/search
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import get_graph_serializer, get_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["Graph"])


@router.get("/{owner}/{repo}/full")
async def graph_full(owner: str, repo: str, q: Optional[str] = Query(None)):
    """Return the full dependency graph (or search-filtered subgraph).

    Identical to the legacy architecture graph endpoint but routed under the
    /api/graph/ namespace and consumed by InteractiveDependencyGraph.tsx.
    """
    repo_name = f"{owner}/{repo}"
    if not get_graph_service().graph_exists(repo_name):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No dependency graph found for '{repo_name}'. "
                "Please analyze the repository first."
            ),
        )
    try:
        data = await asyncio.to_thread(
            get_graph_serializer().get_full_graph, repo_name, q
        )
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("graph_full failed for %s: %s", repo_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/neighbors/{node_path:path}")
async def graph_neighbors(owner: str, repo: str, node_path: str):
    """Return the immediate neighbourhood of a single node.

    Returns the focal node + all direct predecessors (files that import it)
    and successors (files it imports), plus edges between them.
    """
    repo_name = f"{owner}/{repo}"
    if not get_graph_service().graph_exists(repo_name):
        raise HTTPException(
            status_code=404,
            detail=f"No graph found for '{repo_name}'.",
        )
    try:
        data = await asyncio.to_thread(
            get_graph_serializer().get_neighbors, repo_name, node_path
        )
        if data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "graph_neighbors failed for %s / %s: %s",
            repo_name,
            node_path,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/trace/{node_path:path}")
async def graph_trace(
    owner: str,
    repo: str,
    node_path: str,
    direction: str = Query("both", description="forward | backward | both"),
    depth: int = Query(6, ge=1, le=12, description="BFS depth limit"),
):
    """Trace all reachable dependencies from a node via BFS.

    direction=forward  → files this node depends on (what it imports)
    direction=backward → files that depend on this node (its consumers)
    direction=both     → both directions (default)
    """
    repo_name = f"{owner}/{repo}"
    if not get_graph_service().graph_exists(repo_name):
        raise HTTPException(
            status_code=404,
            detail=f"No graph found for '{repo_name}'.",
        )
    if direction not in ("forward", "backward", "both"):
        raise HTTPException(
            status_code=400,
            detail="direction must be forward, backward, or both.",
        )
    try:
        data = await asyncio.to_thread(
            get_graph_serializer().get_trace, repo_name, node_path, direction, depth
        )
        if data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "graph_trace failed for %s / %s: %s",
            repo_name,
            node_path,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/search")
async def graph_search(
    owner: str,
    repo: str,
    q: str = Query(..., min_length=1),
):
    """Search for nodes whose file path or label matches the query.

    Returns matching nodes highlighted, with their immediate neighbours for
    context.  Matched nodes carry highlighted=true in the response.
    """
    repo_name = f"{owner}/{repo}"
    if not get_graph_service().graph_exists(repo_name):
        raise HTTPException(
            status_code=404,
            detail=f"No graph found for '{repo_name}'.",
        )
    try:
        data = await asyncio.to_thread(get_graph_serializer().get_search, repo_name, q)
        if data.get("error"):
            raise HTTPException(status_code=404, detail=data["error"])
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("graph_search failed for %s: %s", repo_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
