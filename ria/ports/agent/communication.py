"""Communication Bus Port Definition."""

from typing import Protocol, Any


class CommunicationBusPort(Protocol):
    """Port interface for communication bus."""

    def publish(self, topic: str, message: Any) -> None: ...
