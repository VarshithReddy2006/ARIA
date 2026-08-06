"""Dependency Injection Container wiring Infrastructure Adapters to Ports."""

from dataclasses import dataclass, replace

from ria.config.settings import Settings
from ria.infrastructure.filesystem.os_filesystem import OSFilesystemAdapter
from ria.infrastructure.filesystem.workspace_manager import WorkspaceManager
from ria.infrastructure.git.subprocess_git import SubprocessGitAdapter
from ria.infrastructure.storage.sqlite_lock import SQLiteRepositoryLockAdapter
from ria.infrastructure.storage.sqlite_registry import SQLiteRepositoryRegistryAdapter
from ria.infrastructure.system.clock import SystemClockAdapter
from ria.infrastructure.system.hashing import HashlibHashingAdapter
from ria.infrastructure.system.logger import StandardLoggerAdapter
from ria.infrastructure.system.metrics import InMemoryMetricsAdapter
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.index.filesystem import FilesystemPort
from ria.ports.index.hashing import HashingPort
from ria.ports.sync.git import GitClientPort
from ria.ports.sync.lock import RepositoryLockPort
from ria.ports.sync.registry import RepositoryRegistryPort
from ria.ports.sync.workspace import WorkspacePort


@dataclass(frozen=True, slots=True)
class Container:
    """Immutable dependency injection container holding concrete port adapter instances."""

    settings: Settings
    clock: ClockPort
    logger: LoggerPort
    metrics: MetricsPort
    hashing: HashingPort
    filesystem: FilesystemPort
    workspace_manager: WorkspacePort
    repository_registry: RepositoryRegistryPort
    repository_lock: RepositoryLockPort
    git_client: GitClientPort

    @classmethod
    def create(cls, settings: Settings | None = None) -> "Container":
        """Factory method building DI Container instance using provided or default Settings."""
        if settings is None:
            settings = Settings.load_from_env()
        elif settings.environment == "test":
            # This is the legacy composition adapter. Its historical external
            # contract names the isolated environment "testing", while the
            # canonical RIA settings contract deliberately uses "test".
            settings = replace(settings, environment="testing")

        clock_adapter = SystemClockAdapter()
        logger_adapter = StandardLoggerAdapter("ria")
        metrics_adapter = InMemoryMetricsAdapter()
        hashing_adapter = HashlibHashingAdapter()
        fs_adapter = OSFilesystemAdapter()
        workspace_adapter = WorkspaceManager(settings.workspace_base_dir)

        registry_adapter = SQLiteRepositoryRegistryAdapter(settings.sqlite_db_path)
        lock_adapter = SQLiteRepositoryLockAdapter(settings.sqlite_db_path)
        git_adapter = SubprocessGitAdapter(timeout_seconds=settings.git_timeout_seconds)

        return cls(
            settings=settings,
            clock=clock_adapter,
            logger=logger_adapter,
            metrics=metrics_adapter,
            hashing=hashing_adapter,
            filesystem=fs_adapter,
            workspace_manager=workspace_adapter,
            repository_registry=registry_adapter,
            repository_lock=lock_adapter,
            git_client=git_adapter,
        )
