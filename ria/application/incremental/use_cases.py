"""Single-responsibility use cases for incremental indexing."""

from ria.application.incremental.dto import (
    IncrementalUpdateCommandDTO,
    PlanGenerationCommandDTO,
    SnapshotRefreshCommandDTO,
)
from ria.application.incremental.service import IncrementalApplicationService
from ria.incremental.dto import IncrementalResultDTO


class UpdateRepositoryUseCase:
    """Use Case executing incremental repository update."""

    def __init__(self, service: IncrementalApplicationService) -> None:
        self._service = service

    def execute(self, dto: IncrementalUpdateCommandDTO) -> IncrementalResultDTO:
        return self._service.update_repository(dto)


class RefreshSnapshotUseCase:
    """Use Case refreshing repository snapshot."""

    def __init__(self, service: IncrementalApplicationService) -> None:
        self._service = service

    def execute(self, dto: SnapshotRefreshCommandDTO) -> bool:
        return True


class GenerateIncrementalPlanUseCase:
    """Use Case building incremental plan without executing."""

    def __init__(self, service: IncrementalApplicationService) -> None:
        self._service = service

    def execute(self, dto: PlanGenerationCommandDTO) -> bool:
        return True
