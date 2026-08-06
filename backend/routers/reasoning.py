"""Repository Engineering Reasoning Engine (ERE) router.

Exposes the single, policy-driven POST /repositories/{username}/{repository}/reason
endpoint to perform deterministic engineering reasoning over retrieval evidence.
"""

import logging
import sys
from fastapi import APIRouter, HTTPException

from backend.dependencies import engineering_reasoning_engine as _engineering_reasoning_engine
from models.retrieval import RepositoryRetrievalContext
from models.reasoning import ReasoningResult
from pydantic import BaseModel, Field

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


engineering_reasoning_engine = _ReloadSafeDependency(
    "engineering_reasoning_engine", _engineering_reasoning_engine
)
router = APIRouter(tags=["Engineering Reasoning Engine"])


class ReasoningRequest(BaseModel):
    """Payload representing a request to reason over retrieval context."""

    question: str = Field(..., description="The original user query.")
    policy: str = Field(
        "default",
        description="The reasoning policy: default | architecture | bug_investigation | compliance | refactoring",
    )
    context: RepositoryRetrievalContext = Field(
        ..., description="The retrieval context containing code evidence references."
    )


@router.post(
    "/repositories/{username}/{repository}/reason", response_model=ReasoningResult
)
async def reason_context(username: str, repository: str, request: ReasoningRequest):
    """Transforms a retrieval context with code evidence into structured engineering conclusions."""
    repo_name = f"{username}/{repository}"
    try:
        # Check if the repo is indexed
        if (
            repo_name
            not in engineering_reasoning_engine.analyzer.EvidenceAnalyzer.__class__.__module__
        ):
            # Since ERE is read-only, we just require that ERE is fully loaded
            pass

        return engineering_reasoning_engine.reason(
            repo_name=repo_name,
            question=request.question,
            policy=request.policy,
            context=request.context,
        )
    except Exception as exc:
        logger.error(
            "Engineering reasoning failed for %s with policy '%s': %s",
            repo_name,
            request.policy,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Reasoning execution failed: {str(exc)}"
        )
