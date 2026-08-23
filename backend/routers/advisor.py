"""AI Engineering Advisor — REST Router.

Exposes advisor endpoints for generating and querying AdvisorReports,
prioritized recommendations, and engineering roadmaps.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import (
    get_advisor_service,
    get_repository_inspector,
    get_engineering_memory_service,
    get_continuous_monitoring_service,
    get_repository_twin_builder,
)
from models.advisor import AdvisorRecommendation, AdvisorReport, RoadmapPhase
from services.memory_service import RecentHistoryPolicy

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Engineering Advisor"])


def _gather_intelligence(repo_name: str) -> Dict[str, Any]:
    """Collects all available platform intelligence for a repository.

    Returns a dict of optional source payloads. Never raises — absent
    sources are returned as None so the pipeline degrades gracefully.
    """
    sources: Dict[str, Any] = {
        "inspection_report": None,
        "reasoning_result": None,
        "memory_context": None,
        "monitoring_run": None,
        "graph_rag_result": None,
    }

    # Verify the repository is indexed (raises 404 if not)
    try:
        get_repository_twin_builder().build_twin(repo_name)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' is not indexed. Please index it first. ({exc})",
        )

    # Latest inspection report (source: ARI)
    try:
        report = get_repository_inspector().load_latest(repo_name)
        if report:
            sources["inspection_report"] = report.model_dump()
    except Exception as exc:
        logger.warning("Could not load inspection report for '%s': %s", repo_name, exc)

    # Engineering Memory (source: MemoryNavigator)
    try:
        memory_ctx = get_engineering_memory_service().navigator.get_memory_context(
            repo_name, RecentHistoryPolicy(limit=5)
        )
        sources["memory_context"] = memory_ctx.model_dump()
    except Exception as exc:
        logger.warning("Could not load memory context for '%s': %s", repo_name, exc)

    # Latest monitoring run (source: CRM)
    try:
        run = get_continuous_monitoring_service().load_latest_run(repo_name)
        if run:
            sources["monitoring_run"] = run.model_dump()
    except Exception as exc:
        logger.warning("Could not load monitoring run for '%s': %s", repo_name, exc)

    return sources


@router.post(
    "/repositories/{username}/{repository}/advisor",
    response_model=AdvisorReport,
    summary="Generate AI Engineering Advisor Report",
)
async def generate_advisor_report(username: str, repository: str):
    """Runs the full AEA pipeline and returns a structured AdvisorReport.

    Consolidates intelligence from all platform layers:
    Repository Inspector, Engineering Memory, Continuous Monitoring.
    """
    repo_name = f"{username}/{repository}"
    sources = _gather_intelligence(repo_name)

    try:
        report = get_advisor_service().advise(
            repo_name=repo_name,
            inspection_report=sources["inspection_report"],
            reasoning_result=sources["reasoning_result"],
            memory_context=sources["memory_context"],
            monitoring_run=sources["monitoring_run"],
            graph_rag_result=sources["graph_rag_result"],
        )
        return report
    except Exception as exc:
        logger.error(
            "Advisor pipeline failed for '%s': %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Advisor pipeline failed: {str(exc)}"
        )


@router.get(
    "/repositories/{username}/{repository}/advisor/latest",
    response_model=AdvisorReport,
    summary="Get Latest Advisor Report",
)
async def get_latest_report(username: str, repository: str):
    """Returns the most recently persisted AdvisorReport."""
    repo_name = f"{username}/{repository}"
    report = get_advisor_service().load_latest(repo_name)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No advisor report found for '{repo_name}'. Run POST /advisor first.",
        )
    return report


@router.get(
    "/repositories/{username}/{repository}/advisor/recommendations",
    response_model=List[AdvisorRecommendation],
    summary="Get Prioritized Recommendations",
)
async def get_recommendations(
    username: str,
    repository: str,
    priority: Optional[str] = Query(
        None, description="Filter by: critical | high | medium | low"
    ),
    category: Optional[str] = Query(None, description="Filter by category name"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number to return"),
):
    """Returns the prioritized recommendation list from the latest AdvisorReport."""
    repo_name = f"{username}/{repository}"
    report = get_advisor_service().load_latest(repo_name)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No advisor report found for '{repo_name}'. Run POST /advisor first.",
        )

    recs = report.recommendations
    if priority:
        recs = [r for r in recs if r.priority == priority.lower()]
    if category:
        recs = [r for r in recs if r.category == category.lower()]
    return recs[:limit]


@router.get(
    "/repositories/{username}/{repository}/advisor/roadmap",
    response_model=List[RoadmapPhase],
    summary="Get Engineering Roadmap",
)
async def get_roadmap(username: str, repository: str):
    """Returns the phased engineering roadmap from the latest AdvisorReport."""
    repo_name = f"{username}/{repository}"
    report = get_advisor_service().load_latest(repo_name)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No advisor report found for '{repo_name}'. Run POST /advisor first.",
        )
    return report.roadmap
