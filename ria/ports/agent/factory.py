"""Agent Factory Port Definition."""

from typing import Protocol, Any
from ria.domain.models.agent_definition import AgentDefinition


class AgentFactoryPort(Protocol):
    """Port interface for creating agents."""

    def create_agent(self, definition: AgentDefinition) -> Any: ...
