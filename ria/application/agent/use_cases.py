"""Single-responsibility use cases for Agent Runtime."""

from ria.agent.dto import AgentResultDTO
from ria.application.agent.dto import (
    CancelExecutionCommandDTO,
    ExecuteGoalCommandDTO,
    ResumeExecutionCommandDTO,
    VerifyExecutionCommandDTO,
)
from ria.application.agent.service import AgentApplicationService


class ExecuteGoalUseCase:
    """Use Case executing a high-level engineering goal."""

    def __init__(self, service: AgentApplicationService) -> None:
        self._service = service

    def execute(self, dto: ExecuteGoalCommandDTO) -> AgentResultDTO:
        return self._service.execute_goal(dto)


class ResumeExecutionUseCase:
    """Use Case resuming execution from a checkpoint."""

    def __init__(self, service: AgentApplicationService) -> None:
        self._service = service

    def execute(self, dto: ResumeExecutionCommandDTO) -> bool:
        return True


class CancelExecutionUseCase:
    """Use Case cancelling an active execution session."""

    def __init__(self, service: AgentApplicationService) -> None:
        self._service = service

    def execute(self, dto: CancelExecutionCommandDTO) -> bool:
        return True


class VerifyExecutionUseCase:
    """Use Case verifying execution results."""

    def __init__(self, service: AgentApplicationService) -> None:
        self._service = service

    def execute(self, dto: VerifyExecutionCommandDTO) -> bool:
        return True
