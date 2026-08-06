"""Integration tests for SqliteAgentPlatformStore (Phase 12)."""

from __future__ import annotations

import pytest

from ria.domain.models.agent_result import AgentStatistics, ExecutionReport
from ria.infrastructure.storage.sqlite.agent_store import SqliteAgentPlatformStore
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner


@pytest.fixture
def agent_db() -> ConnectionProvider:
    provider = ConnectionProvider(":memory:")
    runner = MigrationRunner(provider)
    runner.run()
    return provider


def test_sqlite_agent_platform_store(agent_db: ConnectionProvider) -> None:
    store = SqliteAgentPlatformStore(agent_db)

    stats = AgentStatistics(tasks_scheduled=2, tasks_succeeded=2, tasks_failed=0)
    report = ExecutionReport(
        session_id="session1",
        summary_text="Multi-agent platform summary",
        statistics=stats,
    )

    store.put_report(report)
    retrieved = store.get_report("session1")

    assert retrieved is not None
    assert retrieved.session_id == "session1"
    assert "Multi-agent" in retrieved.summary_text
    assert retrieved.statistics.tasks_succeeded == 2
