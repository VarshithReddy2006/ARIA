"""Repository Structural Retrieval Engine router.

Exposes a single POST /repositories/{username}/{repository}/retrieve endpoint
supporting policy-driven structural and semantic retrieval plans.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import structural_retrieval_engine
from models.retrieval import RepositoryRetrievalContext

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Repository Structural Retrieval"])


class RetrievalRequest(BaseModel):
    """Payload representing a request to retrieve structured codebase context."""

    question: str = Field(
        ..., description="The user query or question about the codebase."
    )
    policy: str = Field(
        "default",
        description="Retrieval policy: default | architecture | implementation | impact | security | performance",
    )


@router.post(
    "/repositories/{username}/{repository}/retrieve",
    response_model=RepositoryRetrievalContext,
)
async def retrieve_context(username: str, repository: str, request: RetrievalRequest):
    """Converts a repository query into structured context according to the requested retrieval policy."""
    repo_name = f"{username}/{repository}"
    try:
        # Check if the repo is indexed
        if (
            repo_name
            not in structural_retrieval_engine.navigator.get_builder().twin_builder.store
        ):
            raise HTTPException(
                status_code=404, detail=f"Repository '{repo_name}' is not indexed."
            )

        return await structural_retrieval_engine.retrieve(
            repo_name=repo_name,
            question=request.question,
            policy=request.policy,
        )
    except HTTPException:
        raise
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error(
            "Structural retrieval failed for %s with query '%s': %s",
            repo_name,
            request.question,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Retrieval execution failed: {str(exc)}"
        )
