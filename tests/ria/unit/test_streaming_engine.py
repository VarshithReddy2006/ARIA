"""Unit tests for StreamingEngineService (Phase 9)."""

from __future__ import annotations


from ria.application.streaming_engine import StreamingEngineService
from ria.domain.models.reasoning_model import ModelRequest, ProviderConfiguration


def test_streaming_engine_service() -> None:
    svc = StreamingEngineService()
    req = ModelRequest(prompt_text="Hello world stream")
    cfg = ProviderConfiguration("local", "mock-model")

    chunks = list(svc.stream_response(req, cfg))

    assert len(chunks) > 0
    assert chunks[0].chunk_index == 0
    assert chunks[-1].is_final
