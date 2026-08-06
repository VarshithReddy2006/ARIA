"""Unit tests for AgentRegistryService (Phase 4)."""

from __future__ import annotations


from ria.application.agent_registry import AgentRegistryService
from ria.domain.models.agent_id import AgentId


def test_agent_registry_service() -> None:
    registry = AgentRegistryService()
    defs = registry.list_agent_definitions()

    assert len(defs) == 9

    aid_analyst = AgentId.for_agent("analyst", "default")
    d_analyst = registry.get_agent_definition(aid_analyst)

    assert d_analyst is not None
    assert d_analyst.name == "Repository Analyst"
