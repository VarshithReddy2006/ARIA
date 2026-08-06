"""Chat router — Repository Chat v2.

This file is a thin FastAPI router. ALL business logic lives in:
  services/chat/retrieval_pipeline.py

Endpoints (unchanged from v1 — full backward compatibility):
  POST /api/chat          → SSE stream
  POST /api/issues/map    → IssueMapResponse JSON

The only responsibilities of this file are:
  1. Parse and validate the request body
  2. Guard the SSE stream (repo validation)
  3. Delegate to RetrievalPipeline.retrieve_stream()
  4. Return StreamingResponse

No prompt building. No embedding calls. No LLM calls. No retry logic.
"""

import json
import logging
import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from backend.dependencies import (
    chroma_store,
    embedding_service,
    get_retrieval_pipeline,
    graph_rag_service,
)
from models.schemas import IssueMapResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


# ---------------------------------------------------------------------------
# Request models (unchanged — backward compatible)
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")
    message: str = Field(..., description="User message")
    history: List[Dict[str, Any]] = Field(
        default_factory=list, description="Conversation history"
    )
    session_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique conversation identifier for conversation memory",
        max_length=128,
    )

    @field_validator("repo")
    @classmethod
    def repo_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError(
                "repo must not be empty. "
                "Please open a repository from the analysis page first."
            )
        return stripped
    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_empty(cls, value: str) -> str:
        session_id = value.strip()
        if not session_id:
            raise ValueError("session_id must not be empty.")
        return session_id


class IssueMapRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")
    issue: Optional[str] = Field(None, description="GitHub issue text/details")
    title: Optional[str] = Field(None, description="GitHub issue title")
    description: Optional[str] = Field("", description="GitHub issue body/details")


# ---------------------------------------------------------------------------
# GET /api/chat/health — provider status diagnostic
# ---------------------------------------------------------------------------


@router.get("/chat/health")
async def chat_health():
    """Check LLM provider configuration, authentication, and connectivity.

    Runs a live health check against every configured provider.
    Response schema (all existing fields preserved + new fields added):

      status            — "ok" | "degraded" | "unhealthy" | "error"
      provider          — primary provider name
      api_key_present   — true if the primary API key exists in config (backward compat)
      authenticated     — true if the primary provider accepted its credentials
      healthy           — true if the primary provider is reachable and authed
      latency_ms        — health check round-trip latency (primary provider)
      error_type        — classified error type if unhealthy, else null
      error_message     — human-readable diagnosis, never raw SDK exceptions
      recommendation    — actionable fix guidance
      circuit_states    — per-provider circuit breaker states
      all_providers     — health results for every configured provider
      timestamp         — unix epoch of this check
    """
    import time
    from backend.settings import Settings
    from services.llm import ProviderFactory

    current_settings = Settings()
    primary_name = current_settings.llm_provider.lower()

    # ── Backward-compat: api_key_present check ──────────────────────────
    if primary_name == "gemini":
        api_key_present = bool(current_settings.gemini_api_key)
    else:
        api_key_present = bool(current_settings.deepseek_api_key)

    # ── Run live health checks on all configured providers ───────────────
    try:
        all_results = await ProviderFactory.validate_all_providers()
    except Exception as exc:
        logger.error(
            "chat_health: validate_all_providers raised: %s", exc, exc_info=True
        )
        return JSONResponse(
            {
                "status": "error",
                "provider": primary_name,
                "api_key_present": api_key_present,
                "authenticated": False,
                "healthy": False,
                "error_type": "unknown_provider_error",
                "error_message": "Health check could not be completed.",
                "recommendation": "Check backend logs for details.",
                "circuit_states": [],
                "all_providers": {},
                "timestamp": time.time(),
            },
            status_code=500,
        )

    # ── Circuit breaker states from ProviderManager ──────────────────────
    circuit_states = []
    try:
        pipeline = get_retrieval_pipeline()
        circuit_states = pipeline.provider_manager.provider_status()
    except Exception as exc:
        logger.debug("chat_health: could not get circuit states: %s", exc)

    # ── Build per-provider summary (no secrets) ───────────────────────────
    all_providers_summary = {
        name: {
            "provider": h.provider,
            "model": h.model,
            "healthy": h.healthy,
            "authenticated": h.authenticated,
            "latency_ms": round(h.latency_ms, 1) if h.latency_ms is not None else None,
            "error_type": h.error_type,
            "error_message": h.error_message,
            "recommendation": h.recommendation,
        }
        for name, h in all_results.items()
    }

    # ── Primary provider result ───────────────────────────────────────────
    primary = all_results.get(primary_name)
    healthy = primary.healthy if primary else False
    authenticated = primary.authenticated if primary else False

    # Overall status: ok if primary is healthy, degraded if fallback only, unhealthy if none
    healthy_count = sum(1 for h in all_results.values() if h.healthy)
    if healthy and healthy_count == len(all_results):
        status = "ok"
    elif healthy_count > 0:
        status = "degraded"
    else:
        status = "unhealthy"

    return JSONResponse(
        {
            "status": status,
            # ── Backward-compatible fields ──────────────────────────────────
            "provider": primary_name,
            "api_key_present": api_key_present,
            "circuit_states": circuit_states,
            # ── New fields ──────────────────────────────────────────────────
            "authenticated": authenticated,
            "healthy": healthy,
            "latency_ms": round(primary.latency_ms, 1)
            if primary and primary.latency_ms
            else None,
            "error_type": primary.error_type if primary else None,
            "error_message": primary.error_message if primary else None,
            "recommendation": primary.recommendation if primary else None,
            "all_providers": all_providers_summary,
            "configured_providers": list(all_results.keys()),
            "healthy_providers": [name for name, h in all_results.items() if h.healthy],
            "unavailable_providers": [
                name for name, h in all_results.items() if not h.healthy
            ],
            "circuit_breaker_states": circuit_states,
            "configured_models": {name: h.model for name, h in all_results.items()},
            "timestamp": time.time(),
        }
    )


@router.post("/chat/reload")
async def chat_reload():
    """Hot-reload the LLM provider without restarting the backend.

    Call this after updating GEMINI_API_KEY or DEEPSEEK_API_KEY in .env.
    Resets the ProviderFactory cache, ProviderManager, and circuit breakers.
    """
    from services.llm import ProviderFactory
    from backend import dependencies

    # 1. Reset provider factory cache
    ProviderFactory.reset()

    # 2. Reset pipeline's provider manager so it rebuilds with new key
    global_pipeline = dependencies._retrieval_pipeline
    if global_pipeline is not None:
        try:
            from services.chat.provider_manager import ProviderManager

            global_pipeline.provider_manager = ProviderManager()
            logger.info("chat_reload: ProviderManager rebuilt successfully")
        except Exception as exc:
            logger.error("chat_reload: ProviderManager rebuild failed: %s", exc)
            return JSONResponse(
                {"status": "error", "detail": str(exc)}, status_code=500
            )

    # 3. Verify the new provider works
    try:
        new_provider = ProviderFactory.get_provider()
        test_response = await new_provider.generate(
            prompt="Reply with the single word: ready",
            system_instruction="You are a health check assistant.",
        )
        ok = bool(test_response and test_response.strip())
    except Exception as exc:
        logger.error("chat_reload: provider test failed: %s", exc)
        return JSONResponse(
            {
                "status": "error",
                "detail": f"Provider loaded but test call failed: {exc}",
            },
            status_code=500,
        )

    logger.info("chat_reload: provider reloaded and verified OK")
    return JSONResponse(
        {
            "status": "ok",
            "message": "LLM provider reloaded successfully. Chat is ready.",
            "test_response": test_response.strip()[:50] if ok else "",
        }
    )


# ---------------------------------------------------------------------------
# POST /api/chat — SSE streaming endpoint
# ---------------------------------------------------------------------------


@router.post("/chat")
async def repository_chat(request: ChatRequest):
    """Chat with repository context, streaming back token results via SSE.

    v2 Pipeline (all logic in RetrievalPipeline):
      1. Conversation memory + pronoun resolution
      2. Intent detection
      3. Intent routing → Repository Intelligence Layer
      4. Intelligent vector retrieval (top-15 → rerank → dedup → top-5)
      5. Context assembly with token budgeting
      6. ProviderManager streaming (circuit breaker + fallback)
      7. Memory update
      8. Observability emit
    """
    repo_name = request.repo
    question = request.message.strip()
    history = request.history
    session_id = request.session_id

    async def chat_streamer():
        # SSE-level guard (defence-in-depth against empty repo slipping through)
        if not repo_name:
            err = json.dumps(
                {
                    "error": "no_repo_selected",
                    "message": "No repository selected. Please open a repository first.",
                    "status": "done",
                }
            )
            yield f"data: {err}\n\n"
            return

        pipeline = get_retrieval_pipeline()
        try:
            async for sse_event in pipeline.retrieve_stream(
                repo_name=repo_name,
                question=question,
                session_id=session_id,
                history=history,
            ):
                yield sse_event
        except Exception as exc:
            logger.error(
                "Unhandled exception in chat_streamer repo=%s: %s",
                repo_name,
                exc,
                exc_info=True,
            )
            err = json.dumps(
                {
                    "error": "pipeline_error",
                    "message": "An unexpected error occurred. Please try again.",
                    "status": "done",
                }
            )
            yield f"data: {err}\n\n"

    return StreamingResponse(chat_streamer(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# POST /api/issues/map — unchanged from v1
# ---------------------------------------------------------------------------


@router.post("/issues/map", response_model=IssueMapResponse)
async def map_issue(request: IssueMapRequest):
    """Analyse a GitHub issue and return the implementation plan and relevant files."""
    from agents.issue_mapper import IssueMapper

    title = request.issue if request.issue else (request.title or "")
    description = "" if request.issue else (request.description or "")

    if not title.strip():
        raise HTTPException(
            status_code=400,
            detail="Issue title or issue text must be provided.",
        )

    try:
        mapper = IssueMapper(
            embedding_service=embedding_service,
            chroma_store=chroma_store,
        )
        plan = await asyncio.to_thread(
            mapper.map_issue, request.repo, title, description
        )
        return plan
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to map issue: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Issue mapping failed: {str(e)}")


# ---------------------------------------------------------------------------
# Graph-RAG Router
# ---------------------------------------------------------------------------

graph_rag_router = APIRouter(tags=["Graph-RAG Chat"])


class GraphRAGRequest(BaseModel):
    question: str = Field(..., description="User query or message.")
    policy: str = Field("default", description="Retrieval & reasoning policy.")
    options: Dict[str, Any] = Field(
        default_factory=dict, description="Configuration options."
    )


@graph_rag_router.post("/repositories/{username}/{repository}/chat")
async def graph_rag_chat(username: str, repository: str, request: GraphRAGRequest):
    repo_name = f"{username}/{repository}"
    # Verify indexed
    if (
        repo_name
        not in graph_rag_service.pipeline.get_retrieval_engine()
        .navigator.get_builder()
        .twin_builder.store
    ):
        raise HTTPException(
            status_code=404, detail=f"Repository '{repo_name}' is not indexed."
        )

    if request.options.get("stream"):

        async def event_generator():
            async for chunk in graph_rag_service.stream_answer(
                repo_name=repo_name,
                question=request.question,
                policy=request.policy,
                options=request.options,
            ):
                yield chunk

        return StreamingResponse(event_generator(), media_type="text/plain")

    return await graph_rag_service.chat(
        repo_name=repo_name,
        question=request.question,
        policy=request.policy,
        options=request.options,
    )
