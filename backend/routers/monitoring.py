"""Continuous Repository Monitoring — REST Router.

Exposes monitoring endpoints for triggering runs, querying history,
health trends, and current status.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import (
    continuous_monitoring_service,
    repository_twin_builder,
    repository_knowledge_graph_builder,
    engineering_memory_service,
)
from models.monitoring import MonitoringRun, MonitoringStatus, RepositoryHealthTrend
from services.continuous_monitoring import (
    CommitThresholdPolicy,
    ImmediatePolicy,
    ManualPolicy,
    TimeBasedPolicy,
)
from services.memory_service import RecentHistoryPolicy

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Continuous Monitoring"])

_POLICY_MAP = {
    "immediate": ImmediatePolicy(),
    "manual": ManualPolicy(),
    "time_based": TimeBasedPolicy(interval_seconds=3600),
    "commit_threshold": CommitThresholdPolicy(threshold=5),
}


def _resolve_context(repo_name: str):
    """Builds twin, KG, and memory context data for a repository."""
    try:
        twin = repository_twin_builder.build_twin(repo_name)
        twin_data = twin.model_dump()
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' not indexed. Please index it first. ({exc})",
        )

    try:
        kg = repository_knowledge_graph_builder.build_graph(repo_name)
        kg_data = kg.model_dump()
    except Exception:
        kg_data = {}

    try:
        memory_ctx = engineering_memory_service.navigator.get_memory_context(
            repo_name, RecentHistoryPolicy(limit=3)
        )
        memory_data = memory_ctx.model_dump()
    except Exception:
        memory_data = None

    return twin_data, kg_data, memory_data


@router.post(
    "/repositories/{username}/{repository}/monitor",
    response_model=MonitoringRun,
    summary="Trigger a Monitoring Run",
)
async def trigger_monitoring(
    username: str,
    repository: str,
    policy: str = Query(
        "immediate",
        description="immediate | manual | commit_threshold | time_based",
    ),
    inspection_policy: str = Query(
        "default",
        description="default | architecture | security | performance | documentation",
    ),
    commit_count: int = Query(
        0, description="Number of new commits (for commit_threshold policy)."
    ),
):
    """Triggers a monitoring run using the selected policy and returns the MonitoringRun record."""
    repo_name = f"{username}/{repository}"
    twin_data, kg_data, memory_data = _resolve_context(repo_name)

    active_policy = _POLICY_MAP.get(policy, ImmediatePolicy())

    repository_event: Dict[str, Any] = {
        "trigger": "manual" if policy == "manual" else "indexing",
        "commit_count": commit_count,
    }

    try:
        run = continuous_monitoring_service.trigger(
            repo_name=repo_name,
            twin_data=twin_data,
            knowledge_graph_data=kg_data,
            memory_context=memory_data,
            repository_event=repository_event,
            policy=active_policy,
            inspection_policy=inspection_policy,
        )
        return run
    except Exception as exc:
        logger.error(
            "Monitoring trigger failed for '%s': %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Monitoring run failed: {str(exc)}"
        )


@router.get(
    "/repositories/{username}/{repository}/monitor/history",
    response_model=List[MonitoringRun],
    summary="Get Monitoring History",
)
async def get_history(
    username: str,
    repository: str,
    limit: int = Query(
        20, ge=1, le=100, description="Maximum number of runs to return."
    ),
):
    """Returns the chronological list of monitoring runs for a repository."""
    repo_name = f"{username}/{repository}"
    runs = continuous_monitoring_service.load_history(repo_name, limit=limit)
    return runs


@router.get(
    "/repositories/{username}/{repository}/monitor/latest",
    response_model=MonitoringRun,
    summary="Get Latest Monitoring Run",
)
async def get_latest_run(username: str, repository: str):
    """Returns the most recent monitoring run record."""
    repo_name = f"{username}/{repository}"
    run = continuous_monitoring_service.load_latest_run(repo_name)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"No monitoring runs found for '{repo_name}'. Trigger one via POST /monitor.",
        )
    return run


@router.get(
    "/repositories/{username}/{repository}/monitor/trends",
    response_model=RepositoryHealthTrend,
    summary="Get Repository Health Trends",
)
async def get_health_trends(username: str, repository: str):
    """Returns the repository health trend generated from monitoring history."""
    repo_name = f"{username}/{repository}"
    trend = continuous_monitoring_service.load_trend(repo_name)
    if not trend:
        raise HTTPException(
            status_code=404,
            detail=f"No health trend data for '{repo_name}'. Run POST /monitor first.",
        )
    return trend


@router.get(
    "/repositories/{username}/{repository}/monitor/status",
    response_model=MonitoringStatus,
    summary="Get Current Monitoring Status",
)
async def get_monitoring_status(username: str, repository: str):
    """Returns the current monitoring status summary for a repository."""
    repo_name = f"{username}/{repository}"
    return continuous_monitoring_service.get_status(repo_name)
