"""Unit tests for ReasoningPipelineService (Phase 5)."""

from __future__ import annotations


from ria.application.reasoning_pipeline import ReasoningPipelineService
from ria.domain.models.prompt_context import PromptContext, PromptSection
from ria.domain.models.reasoning_model import ProviderConfiguration
from ria.infrastructure.models.provider_registry import LocalModelProvider


def test_reasoning_pipeline_service() -> None:
    svc = ReasoningPipelineService()
    sec = PromptSection(title="Section", content="def foo(): pass", token_count=10)
    p_ctx = PromptContext(sections=(sec,), total_tokens=10)

    provider = LocalModelProvider()
    config = ProviderConfiguration("local", "mock-model")

    res = svc.run_pipeline(p_ctx, provider, config)

    assert "section" in res.answer.lower()
    assert res.metadata.model_name == "mock-model"
    assert res.statistics.prompt_tokens == 10
