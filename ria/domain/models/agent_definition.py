"""Agent definition value objects.

Defines AgentRole, AgentCapability, AgentState, and AgentDefinition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from ria.domain.models.agent_id import AgentId

__all__ = ["AgentRole", "AgentCapability", "AgentState", "AgentDefinition"]


class AgentState(str, Enum):
    """Lifecycle state of an AI Agent."""

    IDLE = "idle"
    BUSY = "busy"
    TERMINATED = "terminated"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentRole:
    """Designated role of an AI Agent.

    Attributes:
        role_name: Name of role (e.g. 'analyst', 'reviewer', 'security', 'architect').
        description: Functional role description.
    """

    role_name: str
    description: str = ""


@dataclass(frozen=True)
class AgentCapability:
    """Specific capability supported by an AI Agent.

    Attributes:
        capability_name: Identifier name (e.g. 'dependency_analysis', 'bug_finding').
        description: Description of capability.
    """

    capability_name: str
    description: str = ""


@dataclass(frozen=True)
class AgentDefinition:
    """Definition specification of a specialized AI Agent.

    Attributes:
        agent_id: Unique AgentId.
        name: Display name.
        role: Designated AgentRole.
        capabilities: Tuple of supported AgentCapability items.
        state: Active AgentState.
    """

    agent_id: AgentId
    name: str
    role: AgentRole
    capabilities: Tuple[AgentCapability, ...] = ()
    state: AgentState = AgentState.IDLE
