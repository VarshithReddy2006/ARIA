"""Incremental Engine entry point."""

from ria.domain.snapshot.entities import RepositorySnapshot
from ria.domain.snapshot.value_objects import IncrementalPlan
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.incremental.diff import DiffEnginePort
from ria.ports.incremental.planner import IncrementalPlannerPort
from ria.ports.incremental.scheduler import IncrementalSchedulerPort
from ria.ports.incremental.snapshot import SnapshotManagerPort


class IncrementalEngine:
    """Core IncrementalEngine coordinating SnapshotManager, DiffEngine, IncrementalPlanner, and IncrementalScheduler."""

    def __init__(
        self,
        snapshot_manager: SnapshotManagerPort,
        diff_engine: DiffEnginePort,
        planner: IncrementalPlannerPort,
        scheduler: IncrementalSchedulerPort,
    ) -> None:
        self._snapshots = snapshot_manager
        self._diff = diff_engine
        self._planner = planner
        self._scheduler = scheduler

    def process_incremental_update(
        self,
        repo_id: RepositoryIdentity,
        from_commit: CommitReference,
        to_commit: CommitReference,
    ) -> IncrementalPlan:
        # 1. Get latest snapshot
        snapshot = self._snapshots.get_latest_snapshot(repo_id)
        if snapshot is None:
            snapshot = self._snapshots.create_snapshot(repo_id, from_commit, total_files=0, total_symbols=0)

        # 2. Compute diff
        changed_files = self._diff.compute_diff(repo_id, from_commit, to_commit)

        # 3. Build incremental plan
        plan = self._planner.build_plan(snapshot, to_commit, changed_files)

        # 4. Execute incremental plan
        self._scheduler.execute_plan(plan)

        # 5. Refresh snapshot to new commit
        self._snapshots.create_snapshot(repo_id, to_commit, total_files=len(plan.files_to_reindex), total_symbols=len(plan.affected_symbols))

        return plan
