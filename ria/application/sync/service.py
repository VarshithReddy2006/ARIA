"""Repository Sync Application Service."""

from typing import Optional

from ria.application.sync.dto import (
    RegisterRepositoryCommand,
    SyncResultDTO,
    SyncStatusDTO,
    SynchronizeRepositoryCommand,
)
from ria.application.sync.exceptions import (
    LockAcquisitionException,
    RepositorySyncException,
)
from ria.domain.common.value_objects import UUIDv4
from ria.domain.sync.entities import RepositoryState
from ria.domain.sync.value_objects import (
    BranchReference,
    CommitReference,
    RepositoryIdentity,
    RepositoryMetadata,
    SyncStatus,
)
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.sync.git import GitClientPort
from ria.ports.sync.lock import RepositoryLockPort
from ria.ports.sync.registry import RepositoryRegistryPort
from ria.ports.sync.workspace import WorkspacePort


class RepositorySyncService:
    """Application Service coordinating workspace allocation, Git commands, registry persistence, and locking."""

    def __init__(
        self,
        git_client: GitClientPort,
        registry: RepositoryRegistryPort,
        lock_manager: RepositoryLockPort,
        workspace_manager: WorkspacePort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._git_client = git_client
        self._registry = registry
        self._lock_manager = lock_manager
        self._workspace_manager = workspace_manager
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def register_repository(self, command: RegisterRepositoryCommand) -> SyncStatusDTO:
        """Register a new repository with UNINITIALIZED state."""
        self._logger.info(
            "Registering repository", remote_url=command.remote_url, name=command.name
        )

        repo_id = RepositoryIdentity(
            repo_id=UUIDv4.generate(),
            remote_url=command.remote_url,
            name=command.name,
        )
        metadata = RepositoryMetadata(
            file_count=0,
            total_bytes=0,
            default_branch=command.default_branch,
            registered_at=self._clock.now_utc(),
        )
        state = RepositoryState(
            identity=repo_id,
            status=SyncStatus.UNINITIALIZED,
            metadata=metadata,
        )

        self._registry.save_state(state)
        self._metrics.increment_counter("repositories_registered_total")

        return SyncStatusDTO(
            repo_id=state.identity.repo_id.value,
            remote_url=state.identity.remote_url,
            name=state.identity.name,
            status=state.status.value,
            current_branch=None,
            current_commit_sha=None,
            file_count=0,
            total_bytes=0,
            last_synced_at=None,
        )

    def synchronize_repository(
        self, command: SynchronizeRepositoryCommand
    ) -> SyncResultDTO:
        """Synchronize repository via clone or fetch within a process lock."""
        start_time = self._clock.monotonic_seconds()
        # Constructed for its validation side effect only: a malformed repo_id must
        # fail fast here rather than midway through the sync flow.
        UUIDv4(value=command.repo_id)

        # Lookup existing state to get remote_url and name
        all_states = self._registry.list_all()
        target_state: Optional[RepositoryState] = None
        for st in all_states:
            if st.identity.repo_id.value == command.repo_id:
                target_state = st
                break

        if target_state is None:
            raise RepositorySyncException(
                f"Repository with ID '{command.repo_id}' is not registered."
            )

        repo_identity = target_state.identity

        # Acquire lock
        if not self._lock_manager.acquire_lock(repo_identity, ttl_seconds=300.0):
            self._logger.warning(
                "Repository is locked by another process", repo_id=command.repo_id
            )
            raise LockAcquisitionException(
                f"Failed to acquire sync lock for repository '{command.repo_id}'."
            )

        try:
            target_state.start_syncing()
            self._registry.save_state(target_state)

            workspace_dir = self._workspace_manager.create_workspace(repo_identity)

            # Determine clone vs fetch
            is_cloned = (workspace_dir / ".git").exists()
            prev_commit: Optional[CommitReference] = target_state.current_commit

            if not is_cloned:
                self._logger.info(
                    "Cloning repository into workspace", repo_id=command.repo_id
                )
                commit = self._git_client.clone(repo_identity.remote_url, workspace_dir)
            else:
                self._logger.info(
                    "Fetching remote updates for workspace", repo_id=command.repo_id
                )
                self._git_client.fetch(workspace_dir)
                target_branch = (
                    command.target_branch or target_state.metadata.default_branch
                )
                commit = self._git_client.checkout(workspace_dir, target_branch)

            # Update metadata
            metadata = self._git_client.get_metadata(
                workspace_dir, target_state.metadata.default_branch
            )
            target_state.metadata = metadata

            # Calculate changes
            files_changed = 0
            if prev_commit and prev_commit.sha != commit.sha:
                changed = self._git_client.detect_changed_files(
                    workspace_dir, prev_commit.sha, commit.sha
                )
                files_changed = len(changed)

            branch_ref = BranchReference(
                name=command.target_branch or metadata.default_branch,
                head_commit=commit,
            )
            now_ts = self._clock.now_utc()
            target_state.mark_synchronized(
                branch=branch_ref, commit=commit, synced_at=now_ts
            )
            self._registry.save_state(target_state)

            elapsed = self._clock.monotonic_seconds() - start_time
            self._metrics.record_duration("sync_duration_seconds", elapsed)
            self._metrics.increment_counter("sync_success_total")

            return SyncResultDTO(
                repo_id=command.repo_id,
                is_success=True,
                status=SyncStatus.SYNCHRONIZED.value,
                current_commit_sha=commit.sha,
                files_changed=files_changed,
                elapsed_seconds=elapsed,
            )
        except Exception as err:
            target_state.mark_failed()
            self._registry.save_state(target_state)
            self._metrics.increment_counter("sync_failure_total")
            self._logger.error(
                "Repository sync failed", exc=err, repo_id=command.repo_id
            )
            raise RepositorySyncException(
                f"Repository synchronization failed for '{command.repo_id}': {err}"
            ) from err
        finally:
            self._lock_manager.release_lock(repo_identity)

    def get_status(self, repo_id: str) -> SyncStatusDTO:
        """Query current synchronization status DTO for a repository."""
        target_state: Optional[RepositoryState] = None
        for st in self._registry.list_all():
            if st.identity.repo_id.value == repo_id:
                target_state = st
                break

        if target_state is None:
            raise RepositorySyncException(f"Repository '{repo_id}' not found.")

        return SyncStatusDTO(
            repo_id=target_state.identity.repo_id.value,
            remote_url=target_state.identity.remote_url,
            name=target_state.identity.name,
            status=target_state.status.value,
            current_branch=target_state.current_branch.name
            if target_state.current_branch
            else None,
            current_commit_sha=target_state.current_commit.sha
            if target_state.current_commit
            else None,
            file_count=target_state.metadata.file_count,
            total_bytes=target_state.metadata.total_bytes,
            last_synced_at=target_state.last_synced_at.iso_format
            if target_state.last_synced_at
            else None,
        )
