"""Git client backed by the git executable.

Why subprocess rather than a library
------------------------------------
The git binary is the reference implementation. Pure-Python git libraries diverge
on exactly the operations this system depends on — recursive tree listing, rename
detection, binary detection — and a divergence there produces a silently wrong
index rather than an error. Subprocess invocation also imposes no additional
dependency and handles repositories of any size without loading objects into the
interpreter's heap.

Safety properties
-----------------
Every invocation:

* passes arguments as a list, never through a shell, so a branch name containing
  shell metacharacters cannot become a command;
* uses ``--`` before user-supplied path arguments where git accepts it, so a path
  beginning with a hyphen cannot be read as an option;
* runs with a timeout from configuration, satisfying the port's requirement that
  a hung subprocess cannot stall a worker;
* runs with credential prompting disabled, so a private repository fails fast
  instead of blocking on terminal input;
* truncates captured standard error, because git can emit unbounded output and an
  error object should not carry megabytes into a log pipeline.

Field separators
----------------
Commit metadata is read with a ``--format`` string using ASCII unit separator
(0x1f) between fields and record separator (0x1e) at the end. These bytes cannot
occur in a git identity or a commit subject, so parsing is unambiguous — unlike
the newline- or tab-delimited formats that break on multi-line commit messages.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Dict, Iterator, List, Optional, Sequence

from ria.config.settings import GitSettings
from ria.domain.errors import (
    GitCommandError,
    GitUnavailableError,
    RefNotFoundError,
)
from ria.observability.logging import get_logger
from ria.ports.git_client import (
    GitVersion,
    RawBranch,
    RawCommit,
    RawCommitSummary,
    RawSignature,
    RawTreeEntry,
)
from ria.ports.metrics import MetricsSink

__all__ = ["SubprocessGitClient"]

_LOGGER = get_logger(__name__)

#: ASCII unit separator, used between fields of a formatted git record.
_FIELD_SEPARATOR = "\x1f"

#: ASCII record separator, used to terminate a formatted git record.
_RECORD_SEPARATOR = "\x1e"

#: Format string for commit metadata. Field order is fixed and parsed positionally.
_COMMIT_FORMAT = (
    _FIELD_SEPARATOR.join(
        ["%H", "%P", "%T", "%an", "%ae", "%aI", "%cn", "%ce", "%cI", "%B"]
    )
    + _RECORD_SEPARATOR
)

#: Number of fields the commit format produces.
_COMMIT_FIELD_COUNT = 10

#: Environment overrides applied to every invocation. Disables interactive
#: credential prompting and any user or system configuration that could change
#: output formatting.
_GIT_ENVIRONMENT = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "GCM_INTERACTIVE": "never",
    "GIT_CONFIG_NOSYSTEM": "1",
    "LC_ALL": "C",
}

#: Metric names emitted by this adapter.
_METRIC_COMMAND_SECONDS = "ria_git_command_seconds"
_METRIC_COMMAND_TOTAL = "ria_git_command_total"
_METRIC_COMMAND_FAILURES = "ria_git_command_failures_total"


class SubprocessGitClient:
    """Read-only git access via the git executable.

    Stateless with respect to repositories: every method takes a repository path,
    so one instance serves every repository in the process.

    Satisfies :class:`~ria.ports.git_client.GitClient`.

    Args:
        settings: Git subprocess configuration.
        metrics: Sink for command counts and durations.
    """

    def __init__(self, settings: GitSettings, metrics: MetricsSink) -> None:
        self._settings = settings
        self._metrics = metrics
        self._version: Optional[GitVersion] = None

    # -- GitClient --------------------------------------------------------

    def version(self) -> GitVersion:
        """Return the version of the git executable, caching the result.

        Cached because provenance records it on every observation and re-invoking
        git for a constant would be pure overhead.

        Raises:
            GitUnavailableError: If git is absent or not runnable.
        """
        if self._version is not None:
            return self._version
        try:
            output = self._run(None, ["--version"], operation="version")
        except FileNotFoundError as exc:
            raise GitUnavailableError(
                "git executable not found",
                {"executable": self._settings.executable},
            ) from exc
        self._version = self._parse_version(output)
        return self._version

    def resolve_ref(self, repository_path: Path, ref: str) -> str:
        """Resolve a ref expression to a full object name.

        Uses ``rev-parse`` with a commit-type peel so that a tag object resolves to
        the commit it points at rather than to the tag object itself. Without the
        peel, an annotated tag would yield an object name that is not a commit and
        every downstream query would fail confusingly.

        Args:
            repository_path: Path of the git directory.
            ref: Branch, tag, SHA, or any expression git accepts.

        Returns:
            The full object name of the commit.

        Raises:
            RefNotFoundError: If the ref does not resolve to a commit.
            GitCommandError: If the invocation fails for another reason.
        """
        if not ref or not ref.strip():
            raise RefNotFoundError(
                "ref must be non-empty", {"path": str(repository_path)}
            )
        expression = f"{ref.strip()}^{{commit}}"
        try:
            output = self._run(
                repository_path,
                ["rev-parse", "--verify", "--end-of-options", expression],
                operation="resolve_ref",
            )
        except GitCommandError as exc:
            raise RefNotFoundError(
                "ref could not be resolved to a commit",
                {"path": str(repository_path), "ref": ref, "stderr": exc.stderr},
            ) from exc
        return output.strip()

    def read_commit(self, repository_path: Path, sha: str) -> RawCommit:
        """Read the metadata of one commit.

        Args:
            repository_path: Path of the git directory.
            sha: Full object name of the commit.

        Returns:
            The commit's metadata.

        Raises:
            RefNotFoundError: If the object does not exist or is not a commit.
            GitCommandError: If the invocation fails.
        """
        try:
            output = self._run(
                repository_path,
                [
                    "show",
                    "--no-patch",
                    "--encoding=UTF-8",
                    f"--format={_COMMIT_FORMAT}",
                    "--end-of-options",
                    sha,
                ],
                operation="read_commit",
            )
        except GitCommandError as exc:
            raise RefNotFoundError(
                "commit could not be read",
                {"path": str(repository_path), "sha": sha, "stderr": exc.stderr},
            ) from exc
        return self._parse_commit(output, sha)

    def list_branches(self, repository_path: Path) -> Sequence[RawBranch]:
        """Enumerate local branches.

        Args:
            repository_path: Path of the git directory.

        Returns:
            Every local branch, with the default branch flagged.

        Raises:
            GitCommandError: If the invocation fails.
        """
        default_branch = self._try_detect_default_branch(repository_path)
        output = self._run(
            repository_path,
            [
                "for-each-ref",
                "--format="
                + _FIELD_SEPARATOR.join(
                    ["%(refname:short)", "%(objectname)", "%(committerdate:iso-strict)"]
                ),
                "refs/heads",
            ],
            operation="list_branches",
        )
        branches: List[RawBranch] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split(_FIELD_SEPARATOR)
            if len(parts) != 3:
                _LOGGER.warning(
                    "skipping unparseable for-each-ref record",
                    extra={"path": str(repository_path), "record": line},
                )
                continue
            name, object_name, committed = parts
            branches.append(
                RawBranch(
                    name=name,
                    head_sha=object_name,
                    is_default=(name == default_branch),
                    last_commit_at=self._parse_timestamp(committed),
                )
            )
        return tuple(branches)

    def detect_default_branch(self, repository_path: Path) -> str:
        """Determine the repository's default branch name.

        Args:
            repository_path: Path of the git directory.

        Returns:
            The default branch name without a ``refs/heads/`` prefix.

        Raises:
            RefNotFoundError: If no default branch can be determined.
        """
        detected = self._try_detect_default_branch(repository_path)
        if detected is None:
            raise RefNotFoundError(
                "default branch could not be determined",
                {"path": str(repository_path)},
            )
        return detected

    def list_tree(self, repository_path: Path, sha: str) -> Sequence[RawTreeEntry]:
        """List every blob reachable from a commit's tree.

        Uses ``ls-tree -r -l -z``: recursive, with sizes, NUL-delimited. NUL
        delimiting is required because a path may legally contain a newline, and a
        line-oriented parse would split one such path into two entries.

        Trees and submodule links are excluded: a tree carries no content, and a
        submodule is ingested as a separate repository per SDD section 3 (L1).

        Args:
            repository_path: Path of the git directory.
            sha: Full object name of the commit.

        Returns:
            One entry per blob, in git's order.

        Raises:
            RefNotFoundError: If the commit does not exist.
            GitCommandError: If the invocation fails.
        """
        try:
            output = self._run(
                repository_path,
                ["ls-tree", "-r", "-l", "-z", "--full-tree", "--end-of-options", sha],
                operation="list_tree",
            )
        except GitCommandError as exc:
            raise RefNotFoundError(
                "tree could not be listed",
                {"path": str(repository_path), "sha": sha, "stderr": exc.stderr},
            ) from exc

        entries: List[RawTreeEntry] = []
        for record in output.split("\0"):
            if not record:
                continue
            entry = self._parse_tree_record(record, repository_path)
            if entry is not None:
                entries.append(entry)
        return tuple(entries)

    def read_blob(self, repository_path: Path, blob_sha: str) -> bytes:
        """Read the raw content of a blob.

        Args:
            repository_path: Path of the git directory.
            blob_sha: Blob object name.

        Returns:
            The blob's bytes.

        Raises:
            GitCommandError: If the object cannot be read.
        """
        return self._run_binary(
            repository_path,
            ["cat-file", "blob", "--end-of-options", blob_sha],
            operation="read_blob",
        )

    @contextmanager
    def open_blob(self, repository_path: Path, blob_sha: str) -> Iterator[IO[bytes]]:
        """Open a blob as a managed binary stream.

        Implemented with :class:`subprocess.Popen` rather than
        :func:`subprocess.run`, because the point of this method is to avoid holding
        the whole object in memory. The process is terminated and reaped in a
        ``finally`` block, so abandoning the stream part-way cannot leak a child.

        Args:
            repository_path: Path of the git directory.
            blob_sha: Blob object name.

        Yields:
            A readable binary stream over the blob's content.

        Raises:
            GitCommandError: If the process cannot be started, or exits non-zero
                after the stream is consumed.
        """
        argv = self._argv(
            repository_path, ["cat-file", "blob", "--end-of-options", blob_sha]
        )
        labels = {"operation": "open_blob"}
        self._metrics.increment(_METRIC_COMMAND_TOTAL, labels=labels)
        try:
            process = subprocess.Popen(  # noqa: S603 - argv list, never a shell
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment(),
            )
        except OSError as exc:
            self._metrics.increment(
                _METRIC_COMMAND_FAILURES, labels={**labels, "reason": "spawn"}
            )
            raise GitCommandError(argv, -1, str(exc)) from exc

        stream = process.stdout
        if stream is None:  # pragma: no cover - Popen always provides a pipe here
            process.kill()
            process.wait()
            raise GitCommandError(argv, -1, "git produced no output stream")

        try:
            yield stream
        finally:
            # Closing before wait signals the child if the caller stopped early,
            # so a partially consumed stream cannot block on a full pipe buffer.
            stream.close()
            if process.poll() is None:
                process.kill()
            process.wait()
            stderr = b"" if process.stderr is None else process.stderr.read()
            if process.stderr is not None:
                process.stderr.close()

        if process.returncode not in (0, -9, None):
            self._metrics.increment(
                _METRIC_COMMAND_FAILURES, labels={**labels, "reason": "exit_code"}
            )
            raise GitCommandError(
                argv,
                process.returncode,
                stderr.decode("utf-8", errors="replace")[
                    : self._settings.max_stderr_capture
                ],
            )

    def clone_mirror(self, origin_url: str, destination: Path) -> None:
        """Create a bare mirror of a repository.

        Cloned into a sibling staging directory and then renamed into place, so a
        failed or interrupted clone never leaves a partial directory that a later
        call would mistake for a usable mirror. The rename is atomic on every
        filesystem this system targets.

        Args:
            origin_url: Upstream URL or local path.
            destination: Directory to create.

        Raises:
            GitCommandError: If the destination already exists, or the clone fails.
        """
        if destination.exists():
            raise GitCommandError(
                ["clone", "--mirror"], -1, f"destination already exists: {destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.incoming"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

        try:
            self._run(
                None,
                [
                    "clone",
                    "--mirror",
                    "--quiet",
                    "--end-of-options",
                    origin_url,
                    str(staging),
                ],
                operation="clone_mirror",
            )
        except GitCommandError:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        try:
            staging.replace(destination)
        except OSError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise GitCommandError(["clone", "--mirror"], -1, str(exc)) from exc

        _LOGGER.info(
            "repository mirror cloned",
            extra={"destination": str(destination)},
        )

    def fetch(self, repository_path: Path, *, prune: bool = True) -> None:
        """Update an existing mirror from its origin.

        Args:
            repository_path: Path of the mirror.
            prune: Whether to delete local refs whose upstream counterpart is gone.

        Raises:
            GitCommandError: If the fetch fails.
        """
        arguments = ["fetch", "--quiet"]
        if prune:
            arguments.extend(["--prune", "--prune-tags"])
        # A mirror's configured refspec already maps every ref, so "origin" alone
        # updates heads and tags. Naming refspecs explicitly here would override
        # that configuration and silently narrow what the mirror tracks.
        arguments.append("origin")
        self._run(repository_path, arguments, operation="fetch")

    def list_commits(
        self,
        repository_path: Path,
        ref: str,
        *,
        limit: int,
        since: Optional[datetime] = None,
    ) -> Sequence[RawCommitSummary]:
        """Walk history from a ref, newest first.

        Uses ``log`` with a unit-separated format rather than ``rev-list``, because
        one invocation returns the sha, parents and timestamp of the whole range.
        Reading full metadata per commit would cost one subprocess per commit, which
        at ten thousand commits dominates discovery entirely.

        Args:
            repository_path: Path of the git directory.
            ref: Starting ref expression.
            limit: Maximum number of commits.
            since: Only include commits at or after this instant.

        Returns:
            Commit summaries, newest first.

        Raises:
            ValueError: If the limit is not positive.
            RefNotFoundError: If the ref does not resolve.
            GitCommandError: If the invocation fails.
        """
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")

        arguments = [
            "log",
            f"--max-count={limit}",
            "--format=" + _FIELD_SEPARATOR.join(["%H", "%P", "%cI"]),
        ]
        if since is not None:
            arguments.append(f"--since={since.astimezone(timezone.utc).isoformat()}")
        arguments.extend(["--end-of-options", ref])

        try:
            output = self._run(repository_path, arguments, operation="list_commits")
        except GitCommandError as exc:
            raise RefNotFoundError(
                "history could not be walked",
                {"path": str(repository_path), "ref": ref, "stderr": exc.stderr},
            ) from exc

        summaries: List[RawCommitSummary] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parts = line.split(_FIELD_SEPARATOR)
            if len(parts) != 3:
                _LOGGER.warning(
                    "skipping unparseable log record",
                    extra={"path": str(repository_path), "record": line},
                )
                continue
            sha, parents, committed = parts
            timestamp = self._parse_timestamp(committed)
            if timestamp is None:
                _LOGGER.warning(
                    "skipping log record with an unparseable timestamp",
                    extra={"path": str(repository_path), "sha": sha},
                )
                continue
            summaries.append(
                RawCommitSummary(
                    sha=sha.strip(),
                    parent_shas=tuple(part for part in parents.split() if part),
                    committed_at=timestamp,
                )
            )
        return tuple(summaries)

    def count_lines(self, data: bytes) -> Optional[int]:
        """Count the lines in file content, or return ``None`` if it is binary.

        Applies git's own heuristic: content containing a NUL byte within the
        first eight kilobytes is binary. Reusing git's definition rather than
        inventing one avoids a second, divergent notion of "binary" appearing in
        the system.

        A final line without a trailing newline is counted, matching what a
        developer sees in an editor.

        Args:
            data: File content.

        Returns:
            Line count for text content, or ``None`` for binary content.
        """
        if b"\x00" in data[:8192]:
            return None
        if not data:
            return 0
        count = data.count(b"\n")
        return count if data.endswith(b"\n") else count + 1

    # -- parsing ----------------------------------------------------------

    @staticmethod
    def _parse_version(output: str) -> GitVersion:
        """Parse ``git --version`` output into a structured version.

        Unparseable components default to zero rather than raising: an unusual
        version string is not a reason to refuse to operate, and the raw string is
        retained for provenance.

        Args:
            output: Raw command output.
        """
        raw = output.strip()
        numbers: List[int] = []
        for token in raw.replace("(", " ").replace(")", " ").split():
            if token[0].isdigit():
                for component in token.split(".")[:3]:
                    digits = "".join(ch for ch in component if ch.isdigit())
                    numbers.append(int(digits) if digits else 0)
                break
        while len(numbers) < 3:
            numbers.append(0)
        return GitVersion(raw=raw, major=numbers[0], minor=numbers[1], patch=numbers[2])

    def _parse_commit(self, output: str, sha: str) -> RawCommit:
        """Parse a formatted commit record.

        Args:
            output: Raw command output.
            sha: Requested object name, for error context.

        Returns:
            The parsed commit.

        Raises:
            GitCommandError: If the record does not have the expected field count.
        """
        record = output.split(_RECORD_SEPARATOR, 1)[0]
        fields = record.split(_FIELD_SEPARATOR)
        if len(fields) != _COMMIT_FIELD_COUNT:
            raise GitCommandError(
                ["show", sha],
                0,
                f"expected {_COMMIT_FIELD_COUNT} fields, got {len(fields)}",
            )
        (
            object_name,
            parents,
            tree,
            author_name,
            author_email,
            authored,
            committer_name,
            committer_email,
            committed,
            message,
        ) = fields

        authored_at = self._parse_timestamp(authored)
        committed_at = self._parse_timestamp(committed)
        if authored_at is None or committed_at is None:
            raise GitCommandError(
                ["show", sha],
                0,
                f"commit {object_name} has an unparseable timestamp",
            )

        return RawCommit(
            sha=object_name.strip(),
            parent_shas=tuple(part for part in parents.split() if part),
            tree_sha=tree.strip(),
            author=RawSignature(
                name=author_name, email=author_email, timestamp=authored_at
            ),
            committer=RawSignature(
                name=committer_name, email=committer_email, timestamp=committed_at
            ),
            message=message,
        )

    def _parse_tree_record(
        self, record: str, repository_path: Path
    ) -> Optional[RawTreeEntry]:
        """Parse one ``ls-tree -l -z`` record.

        Record layout is ``<mode> SP <type> SP <object> SP+ <size> TAB <path>``.
        The size field is right-aligned with variable padding, and is ``-`` for
        non-blob objects.

        Args:
            record: One NUL-delimited record.
            repository_path: Repository the record came from, for log context.

        Returns:
            The parsed entry, or ``None`` if the record is not a blob or cannot be
            parsed. A malformed record is logged and skipped rather than aborting
            the listing, per the L1 failure-mode rule that one bad file must not
            fail a build.
        """
        head, tab, path = record.partition("\t")
        if not tab or not path:
            _LOGGER.warning(
                "skipping unparseable ls-tree record",
                extra={"path": str(repository_path), "record": record},
            )
            return None
        parts = head.split()
        if len(parts) != 4:
            _LOGGER.warning(
                "skipping ls-tree record with unexpected field count",
                extra={"path": str(repository_path), "record": record},
            )
            return None
        mode, object_type, object_name, size = parts
        if object_type != "blob":
            return None
        try:
            size_bytes = int(size)
        except ValueError:
            _LOGGER.warning(
                "skipping ls-tree record with unparseable size",
                extra={"path": str(repository_path), "record": record},
            )
            return None
        return RawTreeEntry(
            path=path, blob_sha=object_name, size_bytes=size_bytes, mode=mode
        )

    @staticmethod
    def _parse_timestamp(value: str) -> Optional[datetime]:
        """Parse an ISO-8601 strict git timestamp into an aware UTC datetime.

        Args:
            value: Timestamp string, for example ``2026-07-25T10:00:00+02:00``.

        Returns:
            The instant in UTC, or ``None`` if the value is empty or unparseable.
        """
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _try_detect_default_branch(self, repository_path: Path) -> Optional[str]:
        """Best-effort default branch detection.

        Three strategies in order of authority: the remote's advertised head, the
        local ``HEAD`` symbolic ref, then a conventional name that exists. Returns
        ``None`` rather than raising so that callers which merely want to flag the
        default branch are not forced to handle an exception.

        Args:
            repository_path: Path of the git directory.
        """
        try:
            output = self._run(
                repository_path,
                ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                operation="detect_default_branch",
            )
            candidate = output.strip()
            if candidate.startswith("origin/"):
                return candidate[len("origin/") :]
            if candidate:
                return candidate
        except GitCommandError:
            pass

        try:
            output = self._run(
                repository_path,
                ["symbolic-ref", "--short", "HEAD"],
                operation="detect_default_branch",
            )
            candidate = output.strip()
            if candidate:
                return candidate
        except GitCommandError:
            pass

        for conventional in ("main", "master", "trunk", "develop"):
            try:
                self._run(
                    repository_path,
                    ["rev-parse", "--verify", "--quiet", f"refs/heads/{conventional}"],
                    operation="detect_default_branch",
                )
                return conventional
            except GitCommandError:
                continue
        return None

    # -- invocation -------------------------------------------------------

    def _argv(
        self, repository_path: Optional[Path], arguments: Sequence[str]
    ) -> List[str]:
        """Build the full command line for an invocation.

        Args:
            repository_path: Repository to operate on, or ``None`` for a
                repository-independent command such as ``--version``.
            arguments: Git subcommand and its arguments.
        """
        argv = [self._settings.executable]
        if repository_path is not None:
            argv.extend(["-C", str(repository_path)])
        argv.extend(arguments)
        return argv

    def _run(
        self,
        repository_path: Optional[Path],
        arguments: Sequence[str],
        *,
        operation: str,
    ) -> str:
        """Invoke git and return decoded standard output.

        Decoding replaces undecodable bytes rather than raising, because commit
        messages and paths in real repositories are not reliably UTF-8 and one
        such object must not abort an index build.

        Args:
            repository_path: Repository to operate on, or ``None``.
            arguments: Git subcommand and its arguments.
            operation: Metric label naming the logical operation.

        Returns:
            Decoded standard output.

        Raises:
            GitCommandError: If git exits non-zero or exceeds its timeout.
        """
        completed = self._execute(repository_path, arguments, operation=operation)
        return completed.decode("utf-8", errors="replace")

    def _run_binary(
        self,
        repository_path: Optional[Path],
        arguments: Sequence[str],
        *,
        operation: str,
    ) -> bytes:
        """Invoke git and return raw standard output.

        Args:
            repository_path: Repository to operate on, or ``None``.
            arguments: Git subcommand and its arguments.
            operation: Metric label naming the logical operation.

        Returns:
            Raw standard output.

        Raises:
            GitCommandError: If git exits non-zero or exceeds its timeout.
        """
        return self._execute(repository_path, arguments, operation=operation)

    def _execute(
        self,
        repository_path: Optional[Path],
        arguments: Sequence[str],
        *,
        operation: str,
    ) -> bytes:
        """Run a git subprocess with timeout, metrics and error translation.

        Args:
            repository_path: Repository to operate on, or ``None``.
            arguments: Git subcommand and its arguments.
            operation: Metric label naming the logical operation.

        Returns:
            Raw standard output.

        Raises:
            GitCommandError: If git exits non-zero or exceeds its timeout.
            FileNotFoundError: If the executable is absent. Translated to
                :class:`~ria.domain.errors.GitUnavailableError` by :meth:`version`,
                which is the only caller that can meaningfully report it.
        """
        argv = self._argv(repository_path, arguments)
        labels = {"operation": operation}
        self._metrics.increment(_METRIC_COMMAND_TOTAL, labels=labels)
        try:
            with self._metrics.timer(_METRIC_COMMAND_SECONDS, labels=labels):
                completed = subprocess.run(  # noqa: S603 - argv list, never a shell
                    argv,
                    capture_output=True,
                    timeout=self._settings.command_timeout_seconds,
                    check=False,
                    env=self._environment(),
                )
        except subprocess.TimeoutExpired as exc:
            self._metrics.increment(
                _METRIC_COMMAND_FAILURES, labels={**labels, "reason": "timeout"}
            )
            raise GitCommandError(
                argv, -1, f"timed out after {self._settings.command_timeout_seconds}s"
            ) from exc

        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace")[
                : self._settings.max_stderr_capture
            ]
            self._metrics.increment(
                _METRIC_COMMAND_FAILURES, labels={**labels, "reason": "exit_code"}
            )
            raise GitCommandError(argv, completed.returncode, stderr)

        return completed.stdout

    @staticmethod
    def _environment() -> Dict[str, str]:
        """Build the environment for a git invocation.

        Inherits the parent environment so that ``PATH`` and any credential helper
        configuration remain available, then applies the overrides that make
        output deterministic and prevent interactive prompting.
        """
        environment = dict(os.environ)
        environment.update(_GIT_ENVIRONMENT)
        return environment
