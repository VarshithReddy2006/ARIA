"""Autonomous Repository Inspector — REST Router.

Exposes inspection endpoints for triggering and querying structured
engineering findings and reports.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import (
    repository_inspector,
    repository_twin_builder,
    repository_knowledge_graph_builder,
    engineering_memory_service,
)
from models.inspection import Finding, InspectionReport
from services.memory_service import RecentHistoryPolicy

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Repository Inspector"])


def _build_context_data(
    repo_name: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]]]:
    """Resolves twin, KG, and memory context data for a repository."""
    # Build twin
    try:
        twin = repository_twin_builder.build_twin(repo_name)
        twin_data = twin.model_dump()
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' is not indexed. Please index and analyze it first. ({exc})",
        )

    # Build knowledge graph
    try:
        kg = repository_knowledge_graph_builder.build_graph(repo_name)
        kg_data = kg.model_dump()
    except Exception:
        kg_data = {}

    # Load lightweight memory context (recent history)
    try:
        memory_ctx = engineering_memory_service.navigator.get_memory_context(
            repo_name, RecentHistoryPolicy(limit=3)
        )
        memory_data = memory_ctx.model_dump()
    except Exception:
        memory_data = None

    return twin_data, kg_data, memory_data


@router.post(
    "/repositories/{username}/{repository}/inspect",
    response_model=InspectionReport,
    summary="Run Autonomous Repository Inspection",
)
async def inspect_repository(
    username: str,
    repository: str,
    policy: str = Query(
        "default",
        description="default | architecture | security | performance | documentation",
    ),
):
    """Runs the full Autonomous Repository Inspector pipeline and returns a structured InspectionReport."""
    repo_name = f"{username}/{repository}"

    twin_data, kg_data, memory_data = _build_context_data(repo_name)

    try:
        report = repository_inspector.inspect(
            repo_name=repo_name,
            twin_data=twin_data,
            knowledge_graph_data=kg_data,
            memory_context=memory_data,
            policy=policy,
        )
        return report
    except Exception as exc:
        logger.error("Inspection failed for '%s': %s", repo_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Inspection failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/inspection/latest",
    response_model=InspectionReport,
    summary="Get Latest Inspection Report",
)
async def get_latest_report(username: str, repository: str):
    """Returns the most recent cached InspectionReport."""
    repo_name = f"{username}/{repository}"
    report = repository_inspector.load_latest(repo_name)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No inspection report found for '{repo_name}'. Run POST /inspect first.",
        )
    return report


@router.get(
    "/repositories/{username}/{repository}/inspection/findings",
    response_model=List[Finding],
    summary="Get Inspection Findings",
)
async def get_findings(
    username: str,
    repository: str,
    severity: Optional[str] = Query(
        None, description="Filter by severity: critical | high | medium | low | info"
    ),
    category: Optional[str] = Query(
        None,
        description="Filter by category: architecture | security | performance | dependency | complexity | dead_code | documentation | testing",
    ),
):
    """Returns deduplicated findings from the latest inspection report, with optional filters."""
    repo_name = f"{username}/{repository}"
    report = repository_inspector.load_latest(repo_name)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No inspection report found for '{repo_name}'. Run POST /inspect first.",
        )

    findings = report.findings
    if severity:
        findings = [f for f in findings if f.severity == severity.lower()]
    if category:
        findings = [f for f in findings if f.category == category.lower()]
    return findings


@router.get(
    "/repositories/{username}/{repository}/inspection/statistics",
    response_model=Dict[str, Any],
    summary="Get Inspection Statistics",
)
async def get_statistics(username: str, repository: str):
    """Returns the statistics block from the latest inspection report."""
    repo_name = f"{username}/{repository}"
    report = repository_inspector.load_latest(repo_name)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"No inspection report found for '{repo_name}'. Run POST /inspect first.",
        )
    return {
        "repository": report.repository,
        "timestamp": report.timestamp,
        "overall_score": report.overall_score,
        **report.statistics,
        "inspection_metadata": report.inspection_metadata,
    }
