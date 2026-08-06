"""Agent Registry application service.

Manages registered specialized AI Agent definitions:
- Repository Analyst
- Code Reviewer
- Dependency Analyst
- Security Reviewer
- Performance Reviewer
- Architecture Reviewer
- Documentation Writer
- Test Planner
- Refactoring Advisor

Implements :class:`~ria.ports.agent.AgentRegistryPort` and :class:`~ria.ports.agent.AgentFactoryPort`.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from ria.domain.models.agent_definition import (
    AgentCapability,
    AgentDefinition,
    AgentRole,
    AgentState,
)
from ria.domain.models.agent_id import AgentId
from ria.ports.agent import AgentFactoryPort, AgentRegistryPort

__all__ = ["AgentRegistryService"]


def _build_default_agents() -> Dict[str, AgentDefinition]:
    definitions: Dict[str, AgentDefinition] = {}

    roles = [
        (
            "analyst",
            "Repository Analyst",
            "Examines repository structures, file units, and symbol relationships.",
            "analysis",
        ),
        (
            "reviewer",
            "Code Reviewer",
            "Performs comprehensive code quality and pattern reviews.",
            "review",
        ),
        (
            "dependency",
            "Dependency Analyst",
            "Analyzes module imports and dependency graphs.",
            "dependency",
        ),
        (
            "security",
            "Security Reviewer",
            "Inspects security vulnerabilities and risk patterns.",
            "security",
        ),
        (
            "performance",
            "Performance Reviewer",
            "Identifies performance bottlenecks and complexity issues.",
            "performance",
        ),
        (
            "architecture",
            "Architecture Reviewer",
            "Evaluates architectural layer integrity and system design.",
            "architecture",
        ),
        (
            "documentation",
            "Documentation Writer",
            "Generates documentation and specification explanations.",
            "documentation",
        ),
        (
            "test_planner",
            "Test Planner",
            "Designs test cases and coverage plans.",
            "testing",
        ),
        (
            "refactoring",
            "Refactoring Advisor",
            "Recommends clean refactoring opportunities.",
            "refactoring",
        ),
    ]

    for key, name, desc, cap_name in roles:
        aid = AgentId.for_agent(key, "default")
        role = AgentRole(role_name=key, description=desc)
        cap = AgentCapability(capability_name=cap_name, description=desc)
        defn = AgentDefinition(
            agent_id=aid,
            name=name,
            role=role,
            capabilities=(cap,),
            state=AgentState.IDLE,
        )
        definitions[aid.value] = defn

    return definitions


class AgentRegistryService(AgentRegistryPort, AgentFactoryPort):
    """Service managing registered specialized agent definitions."""

    def __init__(self) -> None:
        self._definitions: Dict[str, AgentDefinition] = _build_default_agents()

    def get_agent_definition(self, agent_id: AgentId) -> Optional[AgentDefinition]:
        """Look up AgentDefinition by AgentId."""
        return self._definitions.get(agent_id.value)

    def list_agent_definitions(self) -> Tuple[AgentDefinition, ...]:
        """List all registered AgentDefinitions."""
        return tuple(self._definitions.values())

    def create_agent(self, definition: AgentDefinition) -> AgentId:
        """Register a new custom agent definition."""
        self._definitions[definition.agent_id.value] = definition
        return definition.agent_id
