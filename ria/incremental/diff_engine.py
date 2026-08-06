"""Diff Engine implementing DiffEnginePort."""

from collections.abc import Sequence

from ria.domain.snapshot.value_objects import ChangedFile, ChangedFileType
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.incremental.diff import DiffEnginePort
from ria.ports.sync.git import GitClientPort
from ria.ports.sync.workspace import WorkspacePort


class DiffEngine(DiffEnginePort):
    """Engine using GitClientPort to detect changed files between two commits."""

    def __init__(
        self,
        git_client: GitClientPort,
        workspace_manager: WorkspacePort,
    ) -> None:
        self._git = git_client
        self._workspace = workspace_manager

    def compute_diff(
        self,
        repo_id: RepositoryIdentity,
        from_commit: CommitReference,
        to_commit: CommitReference,
    ) -> Sequence[ChangedFile]:
        if from_commit.sha == to_commit.sha:
            return ()

        ws_dir = self._workspace.get_workspace_path(repo_id)
        raw_changed = self._git.detect_changed_files(
            ws_dir, from_commit.sha, to_commit.sha
        )

        results: list[ChangedFile] = []
        for fp in raw_changed:
            abs_p = ws_dir / fp.relative_path
            # Infer change type
            if not abs_p.exists():
                ctype = ChangedFileType.DELETED
            else:
                ctype = ChangedFileType.MODIFIED

            results.append(ChangedFile(path=fp, change_type=ctype))

        return tuple(results)
