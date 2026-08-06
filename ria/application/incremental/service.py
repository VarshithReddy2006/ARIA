"""Application Service for Incremental Indexing."""

from typing import Optional

from ria.application.incremental.dto import IncrementalUpdateCommandDTO, PlanGenerationCommandDTO, SnapshotRefreshCommandDTO
from ria.domain.snapshot.entities import RepositorySnapshot
from ria.domain.snapshot.value_objects import IncrementalPlan
from ria.domain.sync.entities import RepositoryState
from ria.domain.sync.value_objects import BranchReference, CommitReference
from ria.incremental.dto import IncrementalResultDTO
from ria.incremental.engine import IncrementalEngine
from ria.ports.common.clock import ClockPort
from ria.ports.common.logger import LoggerPort
from ria.ports.common.metrics import MetricsPort
from ria.ports.sync.git import GitClientPort
from ria.ports.sync.registry import RepositoryRegistryPort
from ria.ports.sync.workspace import WorkspacePort


class IncrementalApplicationService:
    """Application Service coordinating Git fetch, IncrementalEngine execution, and snapshot creation."""

    def __init__(
        self,
        incremental_engine: IncrementalEngine,
        registry: RepositoryRegistryPort,
        git_client: GitClientPort,
        workspace_manager: WorkspacePort,
        clock: ClockPort,
        logger: LoggerPort,
        metrics: MetricsPort,
    ) -> None:
        self._engine = incremental_engine
        self._registry = registry
        self._git = git_client
        self._workspace = workspace_manager
        self._clock = clock
        self._logger = logger
        self._metrics = metrics

    def update_repository(self, dto: IncrementalUpdateCommandDTO) -> IncrementalResultDTO:
        start_t = self._clock.monotonic_seconds()
        self._logger.info("Executing IncrementalApplicationService.update_repository", repo_id=dto.repo_id)

        target_state: Optional[RepositoryState] = None
        for st in self._registry.list_all():
            if st.identity.repo_id.value == dto.repo_id:
                target_state = st
                break

        if target_state is None or target_state.current_commit is None:
            return IncrementalResultDTO(
                repo_id=dto.repo_id,
                from_commit_sha="unknown",
                to_commit_sha="unknown",
                files_reindexed=0,
                files_deleted=0,
                affected_symbols=0,
                elapsed_seconds=0.0,
                is_success=False,
                error_message=f"Repository '{dto.repo_id}' is not registered or synchronized.",
            )

        repo_identity = target_state.identity
        from_commit = target_state.current_commit
        ws_dir = self._workspace.get_workspace_path(repo_identity)

        try:
            # 1. Fetch remote changes and checkout
            self._git.fetch(ws_dir)
            target_branch = dto.target_branch or target_state.metadata.default_branch
            to_commit = self._git.checkout(ws_dir, target_branch)

            # 2. Process incremental update
            plan = self._engine.process_incremental_update(repo_identity, from_commit, to_commit)

            # 3. Update state
            branch_ref = target_state.current_branch or BranchReference(name="main", head_commit=to_commit)
            target_state.mark_synchronized(branch=branch_ref, commit=to_commit, synced_at=self._clock.now_utc())
            self._registry.save_state(target_state)

            elapsed = self._clock.monotonic_seconds() - start_t
            self._metrics.record_duration("incremental_update_seconds", elapsed)

            return IncrementalResultDTO(
                repo_id=dto.repo_id,
                from_commit_sha=from_commit.sha,
                to_commit_sha=to_commit.sha,
                files_reindexed=len(plan.files_to_reindex),
                files_deleted=len(plan.files_to_delete),
                affected_symbols=len(plan.affected_symbols),
                elapsed_seconds=elapsed,
                is_success=True,
            )
        except Exception as err:
            elapsed = self._clock.monotonic_seconds() - start_t
            self._logger.error("Incremental update failed", exc=err, repo_id=dto.repo_id)
            return IncrementalResultDTO(
                repo_id=dto.repo_id,
                from_commit_sha=from_commit.sha,
                to_commit_sha="unknown",
                files_reindexed=0,
                files_deleted=0,
                affected_symbols=0,
                elapsed_seconds=elapsed,
                is_success=False,
                error_message=str(err),
            )
