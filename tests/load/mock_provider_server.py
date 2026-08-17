"""High-fidelity local streaming LLM server for high-concurrency infrastructure capacity benchmarking.

Enables stress-testing ARIA's internal architecture (event loops, ChromaDB, context
assembly, SSE streaming, thread pools) at 100, 200, 500 concurrency without
violating external provider rate limits or quotas.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn


def create_mock_llm_app(
    token_delay_s: float = 0.015,
    tokens_per_response: int = 40,
    fail_rate: float = 0.0,
    simulate_429: bool = False,
) -> FastAPI:
    app = FastAPI(title="Mock LLM Provider")

    @app.get("/v1/models")
    @app.get("/models")
    async def list_models():
        """Health check endpoint for DeepSeek/OpenAI style providers."""
        return {
            "data": [
                {
                    "id": "deepseek-ai/deepseek-v4-flash-0731",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "nvidia",
                }
            ]
        }

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def chat_completions(request: Request):
        """OpenAI/NVIDIA NIM compatible streaming completions."""
        if simulate_429:
            return JSONResponse(
                {
                    "error": {
                        "message": "Rate limit exceeded",
                        "type": "rate_limit_error",
                    }
                },
                status_code=429,
            )

        try:
            body = await request.json()
        except Exception:
            body = {}

        stream = body.get("stream", True)
        if not stream:
            return {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "deepseek-ai/deepseek-v4-flash-0731",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "This is a simulated high-fidelity response for ARIA architecture capacity benchmarking.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }

        async def stream_generator():
            words = (
                "Based on the repository architecture and codebase analysis, "
                "the system utilizes FastAPI for ASGI routing and Starlette middleware. "
                "The core retrieval pipeline coordinates vector indexing in ChromaDB with "
                "Tree-sitter AST parsing and graph-based dependency resolution. "
                "Authentication is enforced via APIKeyMiddleware, and multi-provider failover "
                "manages Gemini and DeepSeek endpoints with per-provider circuit breaking."
            ).split()

            target_tokens = min(tokens_per_response, len(words))
            for i in range(target_tokens):
                word = words[i] + " "
                chunk = {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "deepseek-ai/deepseek-v4-flash-0731",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": word},
                            "finish_reason": None if i < target_tokens - 1 else "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                if token_delay_s > 0:
                    await asyncio.sleep(token_delay_s)

            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    return app


class MockProviderServer:
    """Manages the background lifecycle of the mock LLM server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8999,
        token_delay_s: float = 0.015,
        tokens_per_response: int = 40,
    ):
        self.host = host
        self.port = port
        self.app = create_mock_llm_app(
            token_delay_s=token_delay_s, tokens_per_response=tokens_per_response
        )
        self.server: Optional[uvicorn.Server] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="error",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self._task = asyncio.create_task(self.server.serve())
        # Wait for server to bind
        for _ in range(50):
            if self.server.started:
                break
            await asyncio.sleep(0.05)

    async def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
            if self._task:
                try:
                    await asyncio.wait_for(asyncio.shield(self._task), timeout=1.0)
                except Exception:
                    self._task.cancel()
