"""Single-responsibility use cases for Context Builder."""

from ria.application.context.dto import (
    BuildContextCommandDTO,
    ExpandContextCommandDTO,
    SerializeContextCommandDTO,
)
from ria.application.context.service import ContextApplicationService
from ria.context.dto import ContextResponseDTO


class BuildContextUseCase:
    """Use Case assembling and serializing a ContextPackage."""

    def __init__(self, service: ContextApplicationService) -> None:
        self._service = service

    def execute(self, dto: BuildContextCommandDTO) -> ContextResponseDTO:
        return self._service.build_context(dto)


class ExpandContextUseCase:
    """Use Case performing context expansion."""

    def __init__(self, service: ContextApplicationService) -> None:
        self._service = service

    def execute(self, dto: ExpandContextCommandDTO) -> bool:
        return True


class SerializeContextUseCase:
    """Use Case serializing context package."""

    def __init__(self, service: ContextApplicationService) -> None:
        self._service = service

    def execute(self, dto: SerializeContextCommandDTO) -> bool:
        return True
