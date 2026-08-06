"""Agent Communication Bus application service.

Supports structured message publishing and subscription across agents:
Request, Reply, Broadcast, Progress events, Status events.
Implements :class:`~ria.ports.agent.CommunicationBusPort`.
"""

from __future__ import annotations

from typing import Iterator, List

from ria.domain.models.agent_communication import AgentConversation, AgentMessage
from ria.domain.models.agent_id import AgentId
from ria.ports.agent import CommunicationBusPort

__all__ = ["AgentCommunicationBusService"]


class AgentCommunicationBusService(CommunicationBusPort):
    """Service implementing structured inter-agent communication bus."""

    def __init__(self) -> None:
        self._messages: List[AgentMessage] = []

    def publish(self, message: AgentMessage) -> None:
        """Publish message to communication bus."""
        self._messages.append(message)

    def subscribe(self, recipient_id: AgentId) -> Iterator[AgentMessage]:
        """Subscribe to messages targeting recipient_id or broadcast."""
        for msg in self._messages:
            if msg.recipient_id is None or msg.recipient_id == recipient_id:
                yield msg

    def get_conversation(self) -> AgentConversation:
        """Return full conversation history."""
        return AgentConversation(messages=tuple(self._messages))
