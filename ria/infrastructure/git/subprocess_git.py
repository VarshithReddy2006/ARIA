"""Subprocess implementation of GitClientPort."""

from collections.abc import Sequence
from pathlib import Path

from ria.domain.common.value_objects import Timestamp
from ria.domain.index.value_objects import FilePath
from ria.domain.sync.entities import RepositoryMetadata
from ria.domain.sync.value_objects import CommitReference
from ria.infrastructure.exceptions import GitCommandError
from ria.ports.sync.git import GitClientPort
from utils.subprocess_runner import run_safe_command, SafeSubprocessError


class SubprocessGitAdapter(GitClientPort):
    """Subprocess-based Git client adapter executing git command-line operations safely."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds

    def _run_git(self, cmd: list[str], cwd: Path | None = None) -> str:
        """Run git subcommand with shell=False, timeout, and strict error checking."""
        full_cmd = ["git"] + cmd
        try:
            result = run_safe_command(
                full_cmd,
                cwd=cwd,
                timeout=self._timeout,
                check=True,
            )
            return result.stdout.strip()
        except SafeSubprocessError as err:
            if err.timed_out:
                raise GitCommandError(
                    f"Git command '{' '.join(full_cmd)}' timed out after {self._timeout} seconds."
                ) from err
            raise GitCommandError(
                f"Git command '{' '.join(full_cmd)}' failed with exit code {err.returncode}: {err.stderr.strip()}"
            ) from err
        except OSError as err:
            raise GitCommandError(f"Failed to execute git executable: {err}") from err

    def clone(self, remote_url: str, destination_dir: Path) -> CommitReference:
        """Clone remote git repository to local path and return head commit reference."""
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        self._run_git(["clone", "--quiet", remote_url, str(destination_dir)])
        return self.get_current_commit(destination_dir)

    def fetch(self, repo_dir: Path) -> None:
        """Fetch remote refs and objects for existing cloned repository."""
        self._run_git(["fetch", "--all", "--prune", "--quiet"], cwd=repo_dir)

    def checkout(self, repo_dir: Path, branch_or_sha: str) -> CommitReference:
        """Checkout specified branch name or commit SHA and return checked-out commit reference."""
        try:
            self._run_git(["checkout", "--quiet", branch_or_sha], cwd=repo_dir)
        except Exception:
            pass
        try:
            self._run_git(
                ["reset", "--hard", "--quiet", f"origin/{branch_or_sha}"], cwd=repo_dir
            )
        except Exception:
            pass
        return self.get_current_commit(repo_dir)

    def get_current_commit(self, repo_dir: Path) -> CommitReference:
        """Query current HEAD commit SHA and timestamp."""
        sha = self._run_git(["rev-parse", "HEAD"], cwd=repo_dir)
        time_str = self._run_git(["log", "-1", "--format=%cI", "HEAD"], cwd=repo_dir)
        return CommitReference(sha=sha, committed_at=Timestamp(iso_format=time_str))

    def detect_changed_files(
        self, repo_dir: Path, base_sha: str, head_sha: str
    ) -> Sequence[FilePath]:
        """Compute list of relative FilePaths modified between base_sha and head_sha."""
        raw_diff = self._run_git(
            ["diff", "--name-only", base_sha, head_sha], cwd=repo_dir
        )
        if not raw_diff:
            return ()
        lines = [
            line.strip().replace("\\", "/")
            for line in raw_diff.splitlines()
            if line.strip()
        ]
        return tuple(
            FilePath(relative_path=line) for line in lines if not line.startswith("/")
        )

    def get_metadata(self, repo_dir: Path, default_branch: str) -> RepositoryMetadata:
        """Inspect repository and return file count, total bytes, and default branch metadata."""
        ls_files = self._run_git(["ls-files"], cwd=repo_dir)
        file_list = [f for f in ls_files.splitlines() if f.strip()]
        file_count = len(file_list)

        total_bytes = 0
        for f_rel in file_list:
            f_abs = repo_dir / f_rel
            if f_abs.exists() and f_abs.is_file():
                try:
                    total_bytes += f_abs.stat().st_size
                except OSError:
                    pass

        return RepositoryMetadata(
            file_count=file_count,
            total_bytes=total_bytes,
            default_branch=default_branch,
            registered_at=Timestamp.now(),
        )
