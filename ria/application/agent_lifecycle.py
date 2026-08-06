"""Agent Lifecycle Manager application service.

Manages agent state transitions (IDLE -> BUSY -> IDLE / TERMINATED / FAILED),
reuse, termination, and resource tracking.
Implements :class:`~ria.ports.agent.AgentLifecyclePort`.
"""

from __future__ import annotations

from typing import Dict

from ria.domain.models.agent_definition import AgentState
from ria.domain.models.agent_id import AgentId
from ria.ports.agent import AgentLifecyclePort

__all__ = ["AgentLifecycleService"]


class AgentLifecycleService(AgentLifecyclePort):
    """Service managing agent lifecycle states."""

    def __init__(self) -> None:
        self._agent_states: Dict[str, AgentState] = {}

    def get_state(self, agent_id: AgentId) -> AgentState:
        """Get active state of agent_id."""
        return self._agent_states.get(agent_id.value, AgentState.IDLE)

    def transition_state(self, agent_id: AgentId, new_state: AgentState) -> AgentState:
        """Transition agent_id to new_state."""
        self._agent_states[agent_id.value] = new_state
        return new_state

    def terminate_agent(self, agent_id: AgentId) -> None:
        """Terminate active agent_id."""
        self._agent_states[agent_id.value] = AgentState.TERMINATED
