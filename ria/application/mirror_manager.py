"""Mirror acquisition.

Owns the local mirror of a repository: where it lives, whether it exists, and how it
is created or refreshed.

Why mirrors and not working clones
----------------------------------
Every read this system performs is an object read — ``ls-tree``, ``cat-file``,
``rev-parse``, ``for-each-ref`` — all of which work against a bare repository. A
working tree would double the disk cost of every repository and serve nothing. A
mirror additionally copies every ref, which branch discovery depends on and a plain
clone does not provide.

Why the mirror is a cache
-------------------------
SDD section 6.2 classifies mirrors as "a cache of upstream truth" that "may be
deleted safely". This module treats them accordingly: the path is *derived* from the
repository moniker rather than stored, so the mapping is reproducible and there is no
second piece of state that can drift out of agreement with the repository record. A
deleted mirror is re-acquired on the next request rather than being an error.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from ria.domain.errors import MirrorUnavailableError
from ria.domain.identity import Moniker
from ria.domain.models.repository import Repository
from ria.observability.logging import get_logger, log_context
from ria.ports.git_client import GitClient
from ria.ports.metrics import MetricsSink

__all__ = ["MirrorState", "MirrorManager", "mirror_directory_name"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this service.
_METRIC_ACQUIRED = "ria_mirror_acquired_total"
_METRIC_ACQUIRE_SECONDS = "ria_mirror_acquire_seconds"

#: Characters preserved when deriving a directory name from a moniker. Everything
#: else becomes an underscore, so a moniker can never introduce a path separator or
#: a parent reference and escape the mirror root.
_SAFE_CHARACTERS = frozenset("-_.")


def mirror_directory_name(moniker: Union[Moniker, str]) -> str:
    """Derive a filesystem-safe directory name from a repository moniker.

    Sanitisation is a containment control, not cosmetic: a moniker derives from a
    caller-supplied remote URL, so the derived name must be incapable of traversing
    out of the mirror root regardless of what the URL contained.

    Args:
        moniker: Repository moniker, or its string form.

    Returns:
        A single path segment containing only alphanumerics, hyphens, underscores
        and dots.

    Raises:
        ValueError: If sanitisation would produce an empty name.
    """
    text = str(moniker)
    name = "".join(
        character if character.isalnum() or character in _SAFE_CHARACTERS else "_"
        for character in text
    )
    # A name consisting only of dots would still resolve to a directory traversal
    # once joined, so it is rejected rather than silently rewritten.
    if not name or set(name) <= {"."}:
        raise ValueError(f"moniker does not yield a usable directory name: {text!r}")
    return name


@dataclass(frozen=True)
class MirrorState:
    """Outcome of acquiring a mirror.

    Attributes:
        path: Location of the mirror.
        was_cloned: Whether the mirror was created by this call rather than fetched.
            Distinguished because a first clone is orders of magnitude more expensive
            than a fetch, and a caller reporting progress renders the two
            differently.
        was_fetched: Whether an existing mirror was refreshed by this call.
    """

    path: Path
    was_cloned: bool
    was_fetched: bool

    @property
    def was_reused_unchanged(self) -> bool:
        """Whether an existing mirror was used without contacting the origin."""
        return not self.was_cloned and not self.was_fetched


class MirrorManager:
    """Creates, refreshes and locates local repository mirrors.

    Args:
        git: Read and acquire access to git.
        mirror_root: Directory beneath which every mirror lives.
        metrics: Sink for acquisition counts and durations.
    """

    def __init__(self, git: GitClient, mirror_root: Path, metrics: MetricsSink) -> None:
        self._git = git
        self._mirror_root = Path(mirror_root)
        self._metrics = metrics

    @property
    def mirror_root(self) -> Path:
        """Directory beneath which every mirror lives."""
        return self._mirror_root

    def path_for(self, moniker: Union[Moniker, str]) -> Path:
        """Resolve the mirror directory of a repository.

        Derived rather than stored, so the mapping is reproducible from the
        repository record alone and cannot drift.

        Args:
            moniker: Repository moniker, or its string form.

        Returns:
            Absolute path of the mirror directory. The directory may not exist.
        """
        return self._mirror_root / mirror_directory_name(moniker)

    def exists(self, moniker: Union[Moniker, str]) -> bool:
        """Whether a usable mirror is present.

        A directory alone is not sufficient evidence: an interrupted operation could
        leave one behind. The presence of ``HEAD`` inside it is what makes it a git
        repository, and the clone adapter only moves a directory into place once the
        clone succeeded, so this check cannot see a partial mirror.

        Args:
            moniker: Repository moniker, or its string form.
        """
        path = self.path_for(moniker)
        return path.is_dir() and (path / "HEAD").exists()

    def require(self, moniker: Union[Moniker, str]) -> Path:
        """Return the mirror path, or raise if no mirror is present.

        For callers that must read from a mirror and cannot acquire one themselves —
        a read-only query path, for instance, which should not trigger a clone as a
        side effect of a read.

        Args:
            moniker: Repository moniker, or its string form.

        Returns:
            Absolute path of the mirror.

        Raises:
            MirrorUnavailableError: If no usable mirror is present.
        """
        if not self.exists(moniker):
            raise MirrorUnavailableError(
                "repository mirror is not present; acquire it first",
                {"moniker": str(moniker), "expected_path": str(self.path_for(moniker))},
            )
        return self.path_for(moniker)

    def acquire(self, repository: Repository, *, refresh: bool = True) -> MirrorState:
        """Ensure a mirror exists and is up to date.

        Clones when absent, fetches when present. Both paths are idempotent, so a
        retried acquisition job cannot corrupt the mirror or fail because a previous
        attempt partly succeeded.

        Args:
            repository: Repository to acquire.
            refresh: Whether to fetch when the mirror already exists. Disabling it
                lets a caller reuse a mirror acquired moments earlier without a
                second network round trip, which matters when many commit jobs for
                one repository run in sequence.

        Returns:
            The resulting mirror state.

        Raises:
            GitCommandError: If the clone or fetch fails.
        """
        path = self.path_for(repository.moniker)
        with log_context(
            repository=str(repository.moniker),
            repository_id=str(repository.repository_id),
        ):
            if not self.exists(repository.moniker):
                with self._metrics.timer(
                    _METRIC_ACQUIRE_SECONDS, labels={"operation": "clone"}
                ):
                    self._clone(repository, path)
                self._metrics.increment(_METRIC_ACQUIRED, labels={"outcome": "cloned"})
                return MirrorState(path=path, was_cloned=True, was_fetched=False)

            if not refresh:
                self._metrics.increment(_METRIC_ACQUIRED, labels={"outcome": "reused"})
                return MirrorState(path=path, was_cloned=False, was_fetched=False)

            with self._metrics.timer(
                _METRIC_ACQUIRE_SECONDS, labels={"operation": "fetch"}
            ):
                self._git.fetch(path, prune=True)
            self._metrics.increment(_METRIC_ACQUIRED, labels={"outcome": "fetched"})
            _LOGGER.info("repository mirror refreshed", extra={"path": str(path)})
            return MirrorState(path=path, was_cloned=False, was_fetched=True)

    def discard(self, moniker: Union[Moniker, str]) -> bool:
        """Delete a mirror.

        Safe because a mirror holds no facts: everything derived from it is persisted
        elsewhere, and it can be re-cloned from the origin. Used when a repository is
        purged, and available to an operator reclaiming disk.

        Args:
            moniker: Repository moniker, or its string form.

        Returns:
            ``True`` if a mirror was deleted, ``False`` if none was present.
        """
        path = self.path_for(moniker)
        if not path.exists():
            return False
        shutil.rmtree(path, ignore_errors=True)
        _LOGGER.info("repository mirror discarded", extra={"path": str(path)})
        return not path.exists()

    # -- internals --------------------------------------------------------

    def _clone(self, repository: Repository, path: Path) -> None:
        """Clone a mirror, clearing any unusable directory first.

        A directory without ``HEAD`` is the residue of an interrupted operation. It
        is removed rather than reported, because the clone adapter refuses to write
        into an existing path and an operator has nothing to decide here.

        Args:
            repository: Repository to clone.
            path: Destination directory.
        """
        if path.exists():
            _LOGGER.warning(
                "removing unusable mirror directory before cloning",
                extra={"path": str(path)},
            )
            shutil.rmtree(path, ignore_errors=True)
        self._git.clone_mirror(repository.origin_url, path)
        _LOGGER.info(
            "repository mirror created",
            extra={"path": str(path), "origin_url": repository.origin_url},
        )
