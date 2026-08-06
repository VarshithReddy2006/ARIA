"""Git History & Churn router.

Endpoints:
  POST /api/churn/analyze               (SSE stream)
  GET  /api/churn/{owner}/{repo_name}
  GET  /api/churn/{owner}/{repo_name}/hotspots
  GET  /api/churn/{owner}/{repo_name}/file/{file_path}
  GET  /api/churn/{owner}/{repo_name}/timeline
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.dependencies import git_history_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Git History"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChurnAnalyzeRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")
    since_days: int = Field(365, ge=7, le=3650, description="Days of history to mine")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/churn/analyze")
async def analyze_churn(request: ChurnAnalyzeRequest):
    """Mine git history and compute file churn scores. Streams SSE progress."""
    repo_name = request.repo.strip()
    if not repo_name:
        raise HTTPException(status_code=422, detail="repo must not be empty.")

    async def event_generator():
        try:
            gen = git_history_service.build(repo_name, request.since_days)
            summary = None
            while True:
                try:
                    event = await asyncio.to_thread(next, gen)
                    yield f"data: {json.dumps(event)}\n\n"
                except StopIteration as stop:
                    summary = stop.value
                    break

            if summary is not None:
                yield f"data: {json.dumps({'status': 'result', 'data': summary.model_dump()})}\n\n"

            yield f"data: {json.dumps({'status': 'done'})}\n\n"

        except ValueError as val_err:
            yield f"data: {json.dumps({'status': 'error', 'message': str(val_err)})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"
        except Exception as exc:
            logger.error(
                "Churn analysis SSE error for %s: %s", repo_name, exc, exc_info=True
            )
            yield f"data: {json.dumps({'status': 'error', 'message': str(exc)})}\n\n"
            yield f"data: {json.dumps({'status': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/churn/{owner}/{repo_name}")
async def get_churn_summary(
    owner: str,
    repo_name: str,
    since_days: int = Query(365, ge=7, le=3650),
):
    """Return the full churn summary for a repository."""
    full_name = f"{owner}/{repo_name}"
    summary = await asyncio.to_thread(git_history_service.load, full_name, since_days)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No churn data found for '{full_name}' "
                f"(since_days={since_days}). "
                "Run POST /api/churn/analyze first."
            ),
        )
    return summary.model_dump()


@router.get("/churn/{owner}/{repo_name}/hotspots")
async def get_churn_hotspots(
    owner: str,
    repo_name: str,
    since_days: int = Query(365, ge=7, le=3650),
    top_n: int = Query(25, ge=1, le=100),
):
    """Return the top-N hotspot files (high churn + high centrality)."""
    full_name = f"{owner}/{repo_name}"
    hotspots = await asyncio.to_thread(
        git_history_service.get_hotspots, full_name, since_days, top_n
    )
    if not hotspots:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No churn data found for '{full_name}'. "
                "Run POST /api/churn/analyze first."
            ),
        )
    return {"hotspots": [h.model_dump() for h in hotspots]}


@router.get("/churn/{owner}/{repo_name}/file/{file_path:path}")
async def get_file_churn(
    owner: str,
    repo_name: str,
    file_path: str,
    since_days: int = Query(365, ge=7, le=3650),
):
    """Return churn data for a single file."""
    full_name = f"{owner}/{repo_name}"
    record = await asyncio.to_thread(
        git_history_service.get_file_record, full_name, file_path, since_days
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No churn record found for '{file_path}' in '{full_name}'.",
        )
    return record.model_dump()


@router.get("/churn/{owner}/{repo_name}/timeline")
async def get_churn_timeline(
    owner: str,
    repo_name: str,
    since_days: int = Query(365, ge=7, le=3650),
):
    """Return the weekly commit activity timeline."""
    full_name = f"{owner}/{repo_name}"
    summary = await asyncio.to_thread(git_history_service.load, full_name, since_days)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No churn data found for '{full_name}'. "
                "Run POST /api/churn/analyze first."
            ),
        )
    return {"timeline": [t.model_dump() for t in summary.timeline]}
