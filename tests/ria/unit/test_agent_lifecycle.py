"""Unit tests for AgentLifecycleService (Phase 5)."""

from __future__ import annotations


from ria.application.agent_lifecycle import AgentLifecycleService
from ria.domain.models.agent_definition import AgentState
from ria.domain.models.agent_id import AgentId


def test_agent_lifecycle_service() -> None:
    svc = AgentLifecycleService()
    aid = AgentId.for_agent("analyst", "1")

    assert svc.get_state(aid) == AgentState.IDLE

    svc.transition_state(aid, AgentState.BUSY)
    assert svc.get_state(aid) == AgentState.BUSY

    svc.terminate_agent(aid)
    assert svc.get_state(aid) == AgentState.TERMINATED
