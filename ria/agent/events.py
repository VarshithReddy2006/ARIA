"""Agent Runtime Event Publisher and Event Dataclasses."""

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """Base event dataclass for Agent Runtime lifecycle events."""

    event_type: str
    goal_id: str
    details: str


class EventPublisher:
    """In-memory event publisher for agent lifecycle monitoring."""

    def __init__(self) -> None:
        self._listeners: List[Callable[[AgentEvent], None]] = []

    def subscribe(self, listener: Callable[[AgentEvent], None]) -> None:
        self._listeners.append(listener)

    def publish(self, event: AgentEvent) -> None:
        for listener in self._listeners:
            listener(event)
