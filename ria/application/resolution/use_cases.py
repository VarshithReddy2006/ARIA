"""Use case for resolution and FactStore persistence."""

from ria.application.resolution.dto import FactSummaryDTO, ResolveAndStoreCommand
from ria.application.resolution.service import ResolutionApplicationService


class ResolveAndStoreUseCase:
    """Single-responsibility use case wrapping ResolutionApplicationService."""

    def __init__(self, service: ResolutionApplicationService) -> None:
        self._service = service

    def execute(self, command: ResolveAndStoreCommand) -> FactSummaryDTO:
        return self._service.resolve_and_store(command)
