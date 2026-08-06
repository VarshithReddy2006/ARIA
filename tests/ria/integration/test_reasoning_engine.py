"""Integration tests for Milestone 9 — AI Reasoning Engine (Phase 15)."""

from __future__ import annotations

import pytest

from ria.application.reasoning_service import ReasoningEngineService
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptSection,
)
from ria.domain.models.reasoning_id import ReasoningId
from ria.domain.models.reasoning_model import ProviderConfiguration
from ria.domain.models.reasoning_request import ReasoningRequest
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.reasoning_store import SqliteReasoningCacheStore


from ria.infrastructure.models.provider_registry import LocalModelProvider


@pytest.fixture
def reasoning_engine_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_reasoning_engine_end_to_end(reasoning_engine_db: ConnectionProvider) -> None:
    cache = SqliteReasoningCacheStore(reasoning_engine_db)
    svc = ReasoningEngineService(provider=LocalModelProvider(), cache_store=cache)

    rid = ReasoningId.for_reasoning("mock", "digest1")
    sec = PromptSection(title="Evidence", content="def main(): return 0")
    cit = ContextCitation(repository="repo1", file_path="main.py", symbol_name="main")
    p_ctx = PromptContext(sections=(sec,), citations=(cit,), total_tokens=10)

    config = ProviderConfiguration(provider_name="local", model_name="mock-model")
    req = ReasoningRequest(
        reasoning_id=rid, prompt_context=p_ctx, provider_config=config
    )

    # 1. Execute Reasoning
    res1 = svc.execute_reasoning(req)
    assert res1.answer is not None
    assert len(res1.citations) == 1
    assert res1.validation.is_valid

    # 2. Reasoning Cache Hit
    res2 = svc.execute_reasoning(req)
    assert res2.statistics.cache_hit
