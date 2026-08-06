"""Agent communication domain models.

Defines AgentMessage and AgentConversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from ria.domain.models.agent_id import AgentId

__all__ = ["AgentMessage", "AgentConversation"]


@dataclass(frozen=True)
class AgentMessage:
    """Structured message communicated between agents or published on bus.

    Attributes:
        message_id: Unique message identifier.
        sender_id: Sender AgentId.
        recipient_id: Optional target recipient AgentId (None for broadcast).
        message_type: Message type ('request', 'reply', 'broadcast', 'progress', 'status').
        payload: Message body content payload string.
        timestamp_iso: UTC timestamp.
    """

    message_id: str
    sender_id: AgentId
    message_type: str
    payload: str
    recipient_id: Optional[AgentId] = None
    timestamp_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class AgentConversation:
    """History log of inter-agent messages.

    Attributes:
        messages: Tuple of AgentMessage items.
    """

    messages: Tuple[AgentMessage, ...] = ()
