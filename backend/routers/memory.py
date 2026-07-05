"""Engineering Memory REST Router.

Exposes read-only endpoints to query snapshots, timeline, trends, and comparisons
of repository history.
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import engineering_memory_service
from models.memory import (
    RepositorySnapshot,
    RepositoryTimeline,
    TrendMetric,
    MemoryContext,
    ComparisonResult,
)
from services.memory_service import (
    MemoryPolicy,
    RecentHistoryPolicy,
    ArchitectureHistoryPolicy,
    DependencyHistoryPolicy,
    ComplianceHistoryPolicy,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Engineering Memory"])


def get_policy_strategy(policy_name: str) -> MemoryPolicy:
    """Resolves the policy name to a concrete MemoryPolicy strategy class."""
    p_name = policy_name.lower().strip()
    if p_name == "architecture_history":
        return ArchitectureHistoryPolicy()
    elif p_name == "dependency_history":
        return DependencyHistoryPolicy()
    elif p_name == "compliance_history":
        return ComplianceHistoryPolicy()
    else:
        return RecentHistoryPolicy()


@router.get("/repositories/{username}/{repository}/memory", response_model=MemoryContext)
async def get_memory_context(
    username: str,
    repository: str,
    policy: str = Query("recent_history", description="recent_history | architecture_history | dependency_history | compliance_history"),
):
    """Retrieve bounded historical memory context for reasoning."""
    repo_name = f"{username}/{repository}"
    snapshots = engineering_memory_service.navigator.get_history(repo_name)
    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No Engineering Memory found for repository '{repo_name}'. Index it first.")
    
    strategy = get_policy_strategy(policy)
    return engineering_memory_service.navigator.get_memory_context(repo_name, strategy)


@router.get("/repositories/{username}/{repository}/memory/snapshots", response_model=List[RepositorySnapshot])
async def get_snapshots(username: str, repository: str):
    """Retrieve all facts-only snapshots of the repository."""
    repo_name = f"{username}/{repository}"
    snapshots = engineering_memory_service.navigator.get_history(repo_name)
    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No snapshots found for repository '{repo_name}'.")
    return snapshots


@router.get("/repositories/{username}/{repository}/memory/timeline", response_model=RepositoryTimeline)
async def get_timeline(username: str, repository: str):
    """Retrieve chronological event and snapshot timeline."""
    repo_name = f"{username}/{repository}"
    snapshots = engineering_memory_service.navigator.get_history(repo_name)
    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No timeline found for repository '{repo_name}'.")
    return engineering_memory_service.navigator.get_timeline(repo_name)


@router.get("/repositories/{username}/{repository}/memory/trends", response_model=List[TrendMetric])
async def get_trends(username: str, repository: str):
    """Retrieve calculated trend analytics across snapshots."""
    repo_name = f"{username}/{repository}"
    snapshots = engineering_memory_service.navigator.get_history(repo_name)
    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No trends found for repository '{repo_name}'.")
    return engineering_memory_service.navigator.get_trends(repo_name)


@router.get("/repositories/{username}/{repository}/memory/compare", response_model=ComparisonResult)
async def compare_commits(
    username: str,
    repository: str,
    base: str = Query(..., description="Baseline commit SHA."),
    head: str = Query(..., description="Target commit SHA."),
):
    """Compare two commit snapshots or repository states."""
    repo_name = f"{username}/{repository}"
    try:
        return engineering_memory_service.navigator.compare_commits(repo_name, base, head)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Snapshot comparison failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(exc)}")
