"""Repository Knowledge Graph router.

Provides endpoints to retrieve the full semantic knowledge graph, summaries,
and traverse node neighbors, paths, cycles, blast radius, and entrypoints.
"""

import logging
import sys
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import (
    get_repository_knowledge_graph_builder,
    get_repository_knowledge_graph_navigator,
)
from models.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeGraphSummary,
    KnowledgeGraphNode,
)

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


repository_knowledge_graph_builder = _ReloadSafeDependency(
    "repository_knowledge_graph_builder", get_repository_knowledge_graph_builder
)
repository_knowledge_graph_navigator = _ReloadSafeDependency(
    "repository_knowledge_graph_navigator", get_repository_knowledge_graph_navigator
)
router = APIRouter(tags=["Repository Knowledge Graph"])


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph",
    response_model=KnowledgeGraph,
)
async def get_knowledge_graph(username: str, repository: str):
    """Retrieve the full composed read-only Repository Knowledge Graph."""
    repo_name = f"{username}/{repository}"
    try:
        return repository_knowledge_graph_builder.build_graph(repo_name)
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Failed to build knowledge graph for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to compose Knowledge Graph: {str(exc)}"
        )


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/summary",
    response_model=KnowledgeGraphSummary,
)
async def get_knowledge_graph_summary(username: str, repository: str):
    """Retrieve a stats summary of the Repository Knowledge Graph."""
    repo_name = f"{username}/{repository}"
    try:
        return repository_knowledge_graph_builder.build_graph_summary(repo_name)
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Failed to build graph summary for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compose Knowledge Graph summary: {str(exc)}",
        )


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/node",
    response_model=KnowledgeGraphNode,
)
async def get_graph_node(
    username: str,
    repository: str,
    node_id: str = Query(..., description="Stable node identifier"),
):
    """Finds and returns a specific node in the Knowledge Graph by its stable ID."""
    repo_name = f"{username}/{repository}"
    try:
        # Verify repo is indexed
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        node = repository_knowledge_graph_navigator.find_node(
            repo_name, node_id.strip()
        )
        if not node:
            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_id}' not found in Knowledge Graph.",
            )
        return node
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to query node '%s' in %s: %s",
            node_id,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/neighbors",
    response_model=List[KnowledgeGraphNode],
)
async def get_graph_neighbors(
    username: str,
    repository: str,
    node_id: str = Query(..., description="Stable node ID"),
    edge_type: Optional[str] = Query(
        None, description="Optional relationship type filter"
    ),
):
    """Finds immediate successor and predecessor neighbor nodes, optionally filtering by relationship type."""
    repo_name = f"{username}/{repository}"
    try:
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_knowledge_graph_navigator.find_neighbors(
            repo_name, node_id.strip(), edge_type
        )
    except Exception as exc:
        logger.error(
            "Neighbors query failed for node '%s' in %s: %s",
            node_id,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/path",
    response_model=List[str],
)
async def get_graph_path(
    username: str,
    repository: str,
    source: str = Query(..., description="Source node stable ID"),
    target: str = Query(..., description="Target node stable ID"),
):
    """Finds any simple path of node IDs connecting source and target nodes."""
    repo_name = f"{username}/{repository}"
    try:
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_knowledge_graph_navigator.find_path(
            repo_name, source.strip(), target.strip()
        )
    except Exception as exc:
        logger.error(
            "Path query failed from '%s' to '%s' in %s: %s",
            source,
            target,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/shortest-path",
    response_model=List[str],
)
async def get_shortest_graph_path(
    username: str,
    repository: str,
    source: str = Query(..., description="Source node stable ID"),
    target: str = Query(..., description="Target node stable ID"),
):
    """Finds the shortest sequence of node IDs connecting source and target nodes."""
    repo_name = f"{username}/{repository}"
    try:
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_knowledge_graph_navigator.find_shortest_path(
            repo_name, source.strip(), target.strip()
        )
    except Exception as exc:
        logger.error(
            "Shortest path query failed from '%s' to '%s' in %s: %s",
            source,
            target,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/cycles",
    response_model=List[List[str]],
)
async def get_graph_cycles(username: str, repository: str):
    """Detects and returns all cycles (loops) present in the Knowledge Graph."""
    repo_name = f"{username}/{repository}"
    try:
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_knowledge_graph_navigator.find_cycles(repo_name)
    except Exception as exc:
        logger.error("Cycles query failed for %s: %s", repo_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/impact",
    response_model=List[str],
)
async def get_graph_impact(
    username: str,
    repository: str,
    node_id: str = Query(..., description="Stable node ID"),
):
    """Returns the list of all downstream node IDs affected by the specified node ( blast radius )."""
    repo_name = f"{username}/{repository}"
    try:
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_knowledge_graph_navigator.find_impact(
            repo_name, node_id.strip()
        )
    except Exception as exc:
        logger.error(
            "Impact blast radius query failed for '%s' in %s: %s",
            node_id,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/knowledge-graph/entrypoints",
    response_model=List[KnowledgeGraphNode],
)
async def get_graph_entrypoints(username: str, repository: str):
    """Identifies and returns entrypoint file or symbol nodes (in-degree == 0)."""
    repo_name = f"{username}/{repository}"
    try:
        if repo_name not in repository_knowledge_graph_builder.twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_knowledge_graph_navigator.find_entrypoints(repo_name)
    except Exception as exc:
        logger.error(
            "Entrypoints query failed for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")
