"""Agent Registry Port Definition."""

from typing import Protocol, Optional, Sequence
from ria.domain.models.agent_definition import AgentDefinition
from ria.domain.models.agent_id import AgentId


class AgentRegistryPort(Protocol):
    """Port interface for agent registry."""

    def register(self, definition: AgentDefinition) -> None: ...

    def get(self, agent_id: AgentId) -> Optional[AgentDefinition]: ...

    def list_all(self) -> Sequence[AgentDefinition]: ...
