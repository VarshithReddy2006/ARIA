"""Autonomous Engineering Agent (AEA²) — REST Router.

Exposes execution planning endpoints for generating and querying
ExecutionPlans, batches, and critical paths.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from backend.dependencies import (
    execution_planner_service,
    advisor_service,
    repository_twin_builder,
)
from models.execution import ExecutionBatch, ExecutionPlan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Autonomous Engineering Agent"])


def _require_indexed(repo_name: str) -> None:
    """Raises 404 if the repository has not been indexed."""
    try:
        repository_twin_builder.build_twin(repo_name)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' is not indexed. Please index it first. ({exc})",
        )


@router.post(
    "/repositories/{username}/{repository}/execution-plan",
    response_model=ExecutionPlan,
    summary="Generate Execution Plan",
)
async def generate_execution_plan(username: str, repository: str):
    """Runs the full AEA² pipeline and returns a structured ExecutionPlan.

    Requires a previously generated AdvisorReport as input.
    If no AdvisorReport exists, a 404 is returned.
    """
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)

    advisor_report = advisor_service.load_latest(repo_name)
    if not advisor_report:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No AdvisorReport found for '{repo_name}'. "
                "Run POST /advisor first to generate one."
            ),
        )

    try:
        plan = execution_planner_service.plan(
            repo_name=repo_name,
            advisor_report=advisor_report.model_dump(),
        )
        return plan
    except Exception as exc:
        logger.error("ExecutionPlanner failed for '%s': %s", repo_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Execution planning failed: {str(exc)}")


@router.get(
    "/repositories/{username}/{repository}/execution-plan/latest",
    response_model=ExecutionPlan,
    summary="Get Latest Execution Plan",
)
async def get_latest_plan(username: str, repository: str):
    """Returns the most recently persisted ExecutionPlan."""
    repo_name = f"{username}/{repository}"
    plan = execution_planner_service.load_latest(repo_name)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"No execution plan found for '{repo_name}'. Run POST /execution-plan first.",
        )
    return plan


@router.get(
    "/repositories/{username}/{repository}/execution-plan/batches",
    response_model=List[ExecutionBatch],
    summary="Get Execution Batches",
)
async def get_batches(username: str, repository: str):
    """Returns the ordered execution batches from the latest ExecutionPlan."""
    repo_name = f"{username}/{repository}"
    plan = execution_planner_service.load_latest(repo_name)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"No execution plan found for '{repo_name}'. Run POST /execution-plan first.",
        )
    return plan.batches


@router.get(
    "/repositories/{username}/{repository}/execution-plan/critical-path",
    response_model=Dict[str, Any],
    summary="Get Critical Execution Path",
)
async def get_critical_path(username: str, repository: str):
    """Returns the critical path task IDs and rollback checkpoints from the latest plan."""
    repo_name = f"{username}/{repository}"
    plan = execution_planner_service.load_latest(repo_name)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"No execution plan found for '{repo_name}'. Run POST /execution-plan first.",
        )
    return {
        "repository": plan.repository,
        "critical_path": plan.critical_path,
        "rollback_points": plan.rollback_points,
        "conflicts": [c.model_dump() for c in plan.conflicts],
        "statistics": plan.statistics,
    }
