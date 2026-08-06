"""Agent Orchestrator Port Definition."""

from typing import Protocol
from ria.domain.models.agent_execution import ExecutionSession
from ria.domain.models.agent_result import ExecutionReport


class AgentOrchestratorPort(Protocol):
    """Port interface for agent orchestration."""

    def orchestrate(self, session: ExecutionSession) -> ExecutionReport: ...
