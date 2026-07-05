"""Intelligent IDE Workspace — REST Router.

Exposes workspace panel endpoints for IDE integration.
All endpoints are read-only; no analysis or modification is performed.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.dependencies import workspace_service, repository_twin_builder
from models.workspace import (
    AdvisorPanel,
    ChatSessionMeta,
    ExecutionPanel,
    ExplorerPanel,
    FindingsPanel,
    MonitorPanel,
    OverviewPanel,
    TimelinePanel,
    WorkspaceSnapshot,
    WorkspaceState,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Intelligent IDE Workspace"])


def _require_indexed(repo_name: str) -> None:
    """Raises 404 if repository is not indexed."""
    try:
        repository_twin_builder.build_twin(repo_name)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{repo_name}' is not indexed. Please index it first. ({exc})",
        )


@router.get(
    "/repositories/{username}/{repository}/workspace",
    response_model=WorkspaceSnapshot,
    summary="Get Full Workspace Snapshot",
)
async def get_workspace(
    username: str,
    repository: str,
    file: Optional[str] = Query(None, description="Currently selected file path."),
    symbol: Optional[str] = Query(None, description="Currently selected symbol."),
    panel: str = Query("overview", description="Active workspace panel."),
):
    """Returns the complete IDE workspace snapshot for a repository.

    Composes all panel data from existing platform layers in a single call.
    Missing data (e.g. no advisor report yet) gracefully produces empty panels.
    """
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)

    state = WorkspaceState(
        repository=repo_name,
        selected_file=file,
        selected_symbol=symbol,
        active_panel=panel,
    )

    try:
        return workspace_service.get_workspace(repo_name, state=state)
    except Exception as exc:
        logger.error("Workspace composition failed for '%s': %s", repo_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workspace composition failed: {exc}")


@router.get(
    "/repositories/{username}/{repository}/workspace/overview",
    response_model=OverviewPanel,
    summary="Repository Overview Panel",
)
async def get_overview(username: str, repository: str):
    """Returns the Repository Overview panel (Digital Twin + health summary)."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_overview(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/explorer",
    response_model=ExplorerPanel,
    summary="Repository Explorer Panel",
)
async def get_explorer(username: str, repository: str):
    """Returns the Knowledge Graph explorer panel."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_explorer(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/chat",
    response_model=ChatSessionMeta,
    summary="Engineering Chat Session Metadata",
)
async def get_chat(username: str, repository: str):
    """Returns Graph-RAG chat session metadata for the workspace."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_chat(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/findings",
    response_model=FindingsPanel,
    summary="Engineering Findings Panel",
)
async def get_findings(username: str, repository: str):
    """Returns the ARI findings panel."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_findings(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/timeline",
    response_model=TimelinePanel,
    summary="Repository Timeline Panel",
)
async def get_timeline(username: str, repository: str):
    """Returns the Engineering Memory timeline panel."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_timeline(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/monitor",
    response_model=MonitorPanel,
    summary="Monitoring Dashboard Panel",
)
async def get_monitor(username: str, repository: str):
    """Returns the Continuous Monitoring dashboard panel."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_monitor(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/advisor",
    response_model=AdvisorPanel,
    summary="Advisor Dashboard Panel",
)
async def get_advisor(username: str, repository: str):
    """Returns the AI Engineering Advisor panel."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_advisor(repo_name)


@router.get(
    "/repositories/{username}/{repository}/workspace/execution",
    response_model=ExecutionPanel,
    summary="Execution Planner Panel",
)
async def get_execution(username: str, repository: str):
    """Returns the Autonomous Engineering Agent execution plan panel."""
    repo_name = f"{username}/{repository}"
    _require_indexed(repo_name)
    return workspace_service.get_execution(repo_name)
