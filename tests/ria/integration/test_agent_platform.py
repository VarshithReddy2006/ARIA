"""Integration tests for Milestone 10 — Multi-Agent Developer Platform (Phase 15)."""

from __future__ import annotations

import pytest

from ria.application.agent_platform_service import AgentPlatformService
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptSection,
)
from ria.infrastructure.models.provider_registry import LocalModelProvider
from ria.infrastructure.storage.sqlite.agent_store import SqliteAgentPlatformStore
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.reasoning_store import SqliteReasoningCacheStore
from ria.application.reasoning_service import ReasoningEngineService


@pytest.fixture
def platform_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_agent_platform_end_to_end(platform_db: ConnectionProvider) -> None:
    cache = SqliteReasoningCacheStore(platform_db)
    reasoning_svc = ReasoningEngineService(
        provider=LocalModelProvider(), cache_store=cache
    )
    platform_svc = AgentPlatformService(reasoning_engine=reasoning_svc)

    repo_id = RepositoryId("repo1")
    sha = CommitSha("a" * 40)
    sec = PromptSection(title="Evidence", content="def main(): return 0")
    cit = ContextCitation(repository="repo1", file_path="main.py", symbol_name="main")
    p_ctx = PromptContext(sections=(sec,), citations=(cit,), total_tokens=10)

    # 1. Execute Multi-Agent Platform Query
    report1 = platform_svc.run_platform(
        query_text="Analyze repository security vulnerabilities",
        repository_id=repo_id,
        commit_sha=sha,
        prompt_context=p_ctx,
    )

    assert report1.session_id is not None
    assert report1.statistics.tasks_succeeded >= 2
    assert len(report1.task_results) >= 2

    # 2. Persist Execution Report
    store = SqliteAgentPlatformStore(platform_db)
    store.put_report(report1)
    retrieved = store.get_report(report1.session_id)

    assert retrieved is not None
    assert retrieved.session_id == report1.session_id
