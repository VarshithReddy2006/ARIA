"""Agent Lifecycle Port Definition."""

from typing import Protocol
from ria.domain.models.agent_definition import AgentState
from ria.domain.models.agent_id import AgentId


class AgentLifecyclePort(Protocol):
    """Port interface for agent lifecycle management."""

    def get_state(self, agent_id: AgentId) -> AgentState:
        ...

    def set_state(self, agent_id: AgentId, state: AgentState) -> None:
        ...
