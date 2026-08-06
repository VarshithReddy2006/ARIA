"""Shared fixtures for the ``ria`` test suite.

Every fixture confines its artefacts to a pytest temporary directory. No test
touches the developer's real data root, and no test depends on state left behind by
another, which is what :meth:`ria.config.settings.Settings.for_testing` exists for.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterator, Optional

import pytest

from ria.config.settings import Settings
from ria.container import Container, build_container
from ria.domain.identity import Moniker
from ria.infrastructure.git.subprocess_git_client import SubprocessGitClient
from ria.observability.metrics import InMemoryMetricsSink
from tests.ria.fakes import FrozenClock, InMemoryUnitOfWorkFactory

#: Deterministic identity used for every commit created by the git fixtures, so
#: that authorship assertions do not depend on the developer's git configuration.
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Ada Lovelace",
    "GIT_AUTHOR_EMAIL": "ada@example.com",
    "GIT_COMMITTER_NAME": "Ada Lovelace",
    "GIT_COMMITTER_EMAIL": "ada@example.com",
    "GIT_AUTHOR_DATE": "2026-01-01T09:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T09:00:00+00:00",
    # Prevent any developer or CI global configuration from influencing the
    # fixture repositories. os.devnull is used rather than a literal so the
    # fixtures behave identically on Windows and POSIX hosts.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}


def git_available() -> bool:
    """Whether a usable git executable is present.

    Returns:
        ``True`` if ``git --version`` succeeds.
    """
    if shutil.which("git") is None:
        return False
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, check=True, timeout=30
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


#: Skip marker applied to tests that need a real git executable.
requires_git = pytest.mark.skipif(
    not git_available(), reason="git executable is not available"
)


@pytest.fixture
def metrics() -> InMemoryMetricsSink:
    """An empty in-memory metrics sink."""
    return InMemoryMetricsSink()


@pytest.fixture
def clock() -> FrozenClock:
    """A clock frozen at a fixed instant."""
    return FrozenClock()


@pytest.fixture
def unit_of_work_factory() -> InMemoryUnitOfWorkFactory:
    """A factory over a fresh in-memory state."""
    return InMemoryUnitOfWorkFactory()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings confined to the test's temporary directory."""
    return Settings.for_testing(tmp_path / "data")


@pytest.fixture
def container(settings: Settings) -> Iterator[Container]:
    """A fully wired container over temporary storage.

    Closes the thread's database connection on teardown, as the container's own
    contract requires, so that a Windows temporary directory can be removed.
    """
    built = build_container(settings)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def git_client(settings: Settings, metrics: InMemoryMetricsSink) -> SubprocessGitClient:
    """A real git client configured from the test settings."""
    return SubprocessGitClient(settings.git, metrics)


def run_git(repository: Path, *arguments: str) -> str:
    """Run a git command inside a fixture repository.

    Args:
        repository: Working directory.
        *arguments: Arguments after the ``git`` executable.

    Returns:
        Captured standard output with trailing whitespace removed.

    Raises:
        AssertionError: If the command fails, with stderr included so that a broken
            fixture reports why rather than only that it broke.
    """
    completed = subprocess.run(
        ["git", *arguments],
        cwd=str(repository),
        capture_output=True,
        text=True,
        env=_fixture_environment(),
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(arguments)} failed with {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _fixture_environment() -> Dict[str, str]:
    """Build a minimal, deterministic environment for a fixture git invocation.

    Only the variables git genuinely needs are inherited. ``PATH`` locates the
    executable; ``HOME``, ``USERPROFILE`` and ``SYSTEMROOT`` are required by git on
    POSIX and Windows respectively for temporary files and object lookup. Nothing
    else is passed, so a developer's git configuration cannot influence a fixture
    repository and make a test pass on one machine and fail on another.

    Returns:
        The environment mapping.
    """
    inherited = {
        name: os.environ[name]
        for name in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP")
        if name in os.environ
    }
    inherited.update(_GIT_ENV)
    return inherited


GitRepoBuilder = Callable[..., Path]


@pytest.fixture
def make_git_repo(tmp_path: Path) -> GitRepoBuilder:
    """Return a builder that creates a real git repository on disk.

    The default branch is set with ``symbolic-ref`` before the first commit rather
    than with ``git init -b``, because the latter requires git 2.28 and the former
    works on every version the project supports.

    Returns:
        A callable taking an optional name and file mapping, returning the
        repository path.
    """

    counter = {"value": 0}

    def build(
        name: Optional[str] = None,
        files: Optional[Dict[str, object]] = None,
        *,
        default_branch: str = "main",
        message: str = "initial commit",
    ) -> Path:
        counter["value"] += 1
        directory = tmp_path / (name or f"repo{counter['value']}")
        directory.mkdir(parents=True, exist_ok=True)
        run_git(directory, "init", "--quiet")
        run_git(directory, "symbolic-ref", "HEAD", f"refs/heads/{default_branch}")
        run_git(directory, "config", "user.name", "Ada Lovelace")
        run_git(directory, "config", "user.email", "ada@example.com")
        run_git(directory, "config", "commit.gpgsign", "false")

        contents = files if files is not None else {"README.md": "# fixture\n"}
        write_files(directory, contents)
        run_git(directory, "add", "--all")
        run_git(directory, "commit", "--quiet", "-m", message)
        return directory

    return build


def write_files(repository: Path, files: Dict[str, object]) -> None:
    """Write a mapping of relative path to content into a repository.

    Args:
        repository: Repository root.
        files: Mapping of relative path to ``str`` or ``bytes`` content.
    """
    for relative, content in files.items():
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            # Written as bytes rather than through ``write_text``, which applies
            # platform newline translation and would turn every "\n" in a fixture
            # into "\r\n" on Windows. Content addressing means a translated byte
            # is a different file, so a fixture must write exactly what it states.
            target.write_bytes(str(content).encode("utf-8"))


def commit_files(repository: Path, files: Dict[str, object], message: str) -> str:
    """Write files and create a commit.

    Args:
        repository: Repository root.
        files: Files to write.
        message: Commit message.

    Returns:
        The full object name of the new commit.
    """
    write_files(repository, files)
    run_git(repository, "add", "--all")
    run_git(repository, "commit", "--quiet", "-m", message)
    return run_git(repository, "rev-parse", "HEAD")


def head_sha(repository: Path) -> str:
    """Return the full object name of ``HEAD``.

    Args:
        repository: Repository root.
    """
    return run_git(repository, "rev-parse", "HEAD")


def sample_moniker(owner: str = "acme", name: str = "widgets") -> Moniker:
    """Build a repository moniker for a test.

    Args:
        owner: Owner component.
        name: Repository name component.
    """
    return Moniker.for_repository(host="github.com", owner=owner, name=name)


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Build a timezone-aware UTC datetime.

    Args:
        year: Year.
        month: Month.
        day: Day.
        hour: Hour.
        minute: Minute.
    """
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
