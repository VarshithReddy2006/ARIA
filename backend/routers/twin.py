"""Repository Digital Twin router.

Provides endpoints to retrieve the full twin view, lightweight summaries,
and query code symbols, dependencies, and impact analysis via the navigator.
"""

import logging
import sys
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.dependencies import (
    repository_twin_builder as _repository_twin_builder,
    repository_twin_navigator as _repository_twin_navigator,
)
from models.twin import RepositoryTwin, RepositoryTwinSummary

logger = logging.getLogger(__name__)


class _ReloadSafeDependency:
    """Resolve a compatibility dependency from the currently loaded router module."""

    def __init__(self, name: str, fallback: object) -> None:
        self._name = name
        self._fallback = fallback

    def __getattr__(self, attribute: str) -> object:
        module = sys.modules.get(__name__)
        dependency = getattr(module, self._name, self._fallback)
        if dependency is self:
            dependency = self._fallback
        return getattr(dependency, attribute)


repository_twin_builder = _ReloadSafeDependency(
    "repository_twin_builder", _repository_twin_builder
)
repository_twin_navigator = _ReloadSafeDependency(
    "repository_twin_navigator", _repository_twin_navigator
)
router = APIRouter(tags=["Repository Twin"])


class ImpactRequest(BaseModel):
    issue_text: str = Field(
        ..., description="Description of the proposed changes or user issue."
    )


@router.get("/repositories/{username}/{reponame}/twin", response_model=RepositoryTwin)
async def get_repository_twin(username: str, reponame: str):
    """Retrieve the full composed read-only Repository Digital Twin."""
    repo_name = f"{username}/{reponame}"
    try:
        twin = repository_twin_builder.build_twin(repo_name)
        return twin
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error("Failed to build twin for %s: %s", repo_name, exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to compose Twin: {str(exc)}"
        )


@router.get(
    "/repositories/{username}/{reponame}/twin/summary",
    response_model=RepositoryTwinSummary,
)
async def get_repository_twin_summary(username: str, reponame: str):
    """Retrieve a lightweight summary of the Repository Digital Twin."""
    repo_name = f"{username}/{reponame}"
    try:
        summary = repository_twin_builder.build_twin_summary(repo_name)
        return summary
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Failed to build twin summary for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to compose Twin summary: {str(exc)}"
        )


@router.get("/repositories/{username}/{reponame}/twin/symbol")
async def get_twin_symbol(
    username: str,
    reponame: str,
    name: str = Query(..., description="Symbol identifier name"),
):
    """Find a symbol's definition and references within the Twin."""
    repo_name = f"{username}/{reponame}"
    try:
        # Check repository exists in analysis store first
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        result = repository_twin_navigator.find_symbol(repo_name, name.strip())
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to query symbol '%s' for %s: %s",
            name,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get("/repositories/{username}/{reponame}/twin/file")
async def get_twin_file(
    username: str,
    reponame: str,
    path: str = Query(..., description="Relative path of file"),
):
    """Read a file's content from the local clone repository."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        result = repository_twin_navigator.find_file(repo_name, path.strip())
        return result
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Failed to read file '%s' for %s: %s", path, repo_name, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"File query failed: {str(exc)}")


@router.get("/repositories/{username}/{reponame}/twin/dependencies")
async def get_twin_dependencies(
    username: str,
    reponame: str,
    path: str = Query(..., description="Relative path of file"),
):
    """Walk dependencies (successors) of a file in the dependency graph."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_twin_navigator.find_dependencies(repo_name, path.strip())
    except Exception as exc:
        logger.error(
            "Failed to fetch dependencies for file '%s' in %s: %s",
            path,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get("/repositories/{username}/{reponame}/twin/dependents")
async def get_twin_dependents(
    username: str,
    reponame: str,
    path: str = Query(..., description="Relative path of file"),
):
    """Walk dependents (predecessors) of a file in the dependency graph."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_twin_navigator.find_dependents(repo_name, path.strip())
    except Exception as exc:
        logger.error(
            "Failed to fetch dependents for file '%s' in %s: %s",
            path,
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get("/repositories/{username}/{reponame}/twin/architecture")
async def get_twin_architecture(username: str, reponame: str):
    """Retrieve structural summaries and inter-component relationships."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_twin_navigator.find_architecture(repo_name)
    except Exception as exc:
        logger.error(
            "Failed to fetch architecture for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get("/repositories/{username}/{reponame}/twin/health")
async def get_twin_health(username: str, reponame: str):
    """Retrieve full health scores and letter grade breakdown."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_twin_navigator.find_health(repo_name)
    except Exception as exc:
        logger.error(
            "Failed to fetch health report for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.get("/repositories/{username}/{reponame}/twin/compliance")
async def get_twin_compliance(username: str, reponame: str):
    """Retrieve lightweight compliance summary status."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_twin_navigator.find_compliance(repo_name)
    except Exception as exc:
        logger.error(
            "Failed to fetch compliance summary for %s: %s",
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exc)}")


@router.post("/repositories/{username}/{reponame}/twin/impact")
async def calculate_twin_impact(username: str, reponame: str, request: ImpactRequest):
    """Predict affected files and components for a proposed change description."""
    repo_name = f"{username}/{reponame}"
    try:
        if repo_name not in repository_twin_builder.store:
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )
        return repository_twin_navigator.calculate_impact(
            repo_name, request.issue_text.strip()
        )
    except Exception as exc:
        logger.error(
            "Failed to calculate change impact for %s: %s",
            repo_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Impact calculation failed: {str(exc)}"
        )
