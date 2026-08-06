"""Unit tests for AgentCommunicationBusService (Phase 8)."""

from __future__ import annotations


from ria.application.communication_bus import AgentCommunicationBusService
from ria.domain.models.agent_communication import AgentMessage
from ria.domain.models.agent_id import AgentId


def test_communication_bus_service() -> None:
    bus = AgentCommunicationBusService()
    aid1 = AgentId.for_agent("analyst", "1")
    aid2 = AgentId.for_agent("reviewer", "2")

    msg1 = AgentMessage(
        message_id="m1",
        sender_id=aid1,
        recipient_id=aid2,
        message_type="request",
        payload="Analyze imports",
    )
    msg2 = AgentMessage(
        message_id="m2",
        sender_id=aid1,
        recipient_id=None,
        message_type="broadcast",
        payload="Global update",
    )

    bus.publish(msg1)
    bus.publish(msg2)

    sub_aid2 = list(bus.subscribe(aid2))
    assert len(sub_aid2) == 2

    conv = bus.get_conversation()
    assert len(conv.messages) == 2
