"""Streaming Engine application service.

Supports provider-independent streaming responses, incremental tokens, cancellation, and completion events.
Implements :class:`~ria.ports.reasoning.StreamingPort`.
"""

from __future__ import annotations

from typing import Iterator, Optional

from ria.domain.models.reasoning_model import (
    ModelRequest,
    ProviderConfiguration,
    StreamingChunk,
)
from ria.ports.reasoning import ModelProviderPort, StreamingPort

__all__ = ["StreamingEngineService"]


class StreamingEngineService(StreamingPort):
    """Service for provider-independent streaming of LLM token responses."""

    def __init__(self, provider: Optional[ModelProviderPort] = None) -> None:
        self._provider = provider

    def stream_response(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> Iterator[StreamingChunk]:
        """Stream response chunks for a request using configured model provider."""
        provider = self._provider
        if provider is None:
            # Simple inline streaming fallback for local provider
            words = request.prompt_text.split(" ")
            session_id = f"stream_{config.model_name}"
            for idx, word in enumerate(words):
                is_last = idx == len(words) - 1
                delta = word + ("" if is_last else " ")
                yield StreamingChunk(
                    session_id=session_id,
                    chunk_index=idx,
                    text_delta=delta,
                    is_final=is_last,
                )
        else:
            yield from provider.stream_response(request, config)
