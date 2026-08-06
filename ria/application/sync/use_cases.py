"""Use cases for C0 Repository Sync."""

from ria.application.sync.dto import (
    RegisterRepositoryCommand,
    SyncResultDTO,
    SyncStatusDTO,
    SynchronizeRepositoryCommand,
)
from ria.application.sync.service import RepositorySyncService


class RegisterRepositoryUseCase:
    """Use Case executing new repository registration."""

    def __init__(self, service: RepositorySyncService) -> None:
        self._service = service

    def execute(self, command: RegisterRepositoryCommand) -> SyncStatusDTO:
        return self._service.register_repository(command)


class SynchronizeRepositoryUseCase:
    """Use Case executing repository synchronization."""

    def __init__(self, service: RepositorySyncService) -> None:
        self._service = service

    def execute(self, command: SynchronizeRepositoryCommand) -> SyncResultDTO:
        return self._service.synchronize_repository(command)
