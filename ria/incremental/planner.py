"""Incremental Planner implementing IncrementalPlannerPort."""

from collections.abc import Sequence

from ria.domain.index.value_objects import FilePath
from ria.domain.snapshot.entities import RepositorySnapshot
from ria.domain.snapshot.value_objects import ChangedFile, ChangedFileType, IncrementalPlan
from ria.domain.sync.value_objects import CommitReference
from ria.incremental.dependency_analyzer import DependencyAnalyzer
from ria.ports.incremental.planner import IncrementalPlannerPort


class IncrementalPlanner(IncrementalPlannerPort):
    """Planner constructing IncrementalPlan from snapshot, target commit, and changed file descriptors."""

    def __init__(self, dependency_analyzer: DependencyAnalyzer) -> None:
        self._dep_analyzer = dependency_analyzer

    def build_plan(
        self,
        snapshot: RepositorySnapshot,
        to_commit: CommitReference,
        changed_files: Sequence[ChangedFile],
    ) -> IncrementalPlan:
        files_to_reindex: list[FilePath] = []
        files_to_delete: list[FilePath] = []

        for cf in changed_files:
            if cf.change_type == ChangedFileType.DELETED:
                files_to_delete.append(cf.path)
            else:
                files_to_reindex.append(cf.path)

        impact = self._dep_analyzer.analyze_impact(snapshot.identity, snapshot.commit, changed_files)

        return IncrementalPlan(
            repo_id=snapshot.identity,
            from_commit=snapshot.commit,
            to_commit=to_commit,
            files_to_reindex=tuple(files_to_reindex),
            files_to_delete=tuple(files_to_delete),
            affected_symbols=impact.affected_symbols,
        )
