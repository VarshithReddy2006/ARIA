"""Repository-relative path normalisation.

A single normalisation function used by every layer, so that one path is
represented by exactly one string everywhere in the system. Twin Spec section
3.2 requires file unit paths to be "repo-relative, normalized"; without a single
authority for that, ``src/a.py``, ``./src/a.py`` and ``src\\a.py`` become three
distinct identities for one file and every join silently under-matches.

Normalisation rules
-------------------
* Backslashes become forward slashes, so a Windows host and a Linux host produce
  identical identities for the same repository.
* Redundant ``.`` segments and duplicate separators are removed.
* Leading separators are rejected: paths are relative, never absolute.
* ``..`` segments are rejected outright rather than resolved, because a path
  that escapes the repository root is a security concern, not a formatting one.
"""

from __future__ import annotations

import posixpath
from typing import Sequence

from ria.domain.errors import InvalidPathError

__all__ = [
    "normalise_repository_path",
    "parent_directory",
    "path_segments",
    "is_within",
]


def normalise_repository_path(path: str) -> str:
    """Normalise a repository-relative path to its canonical form.

    Args:
        path: Raw path, possibly using platform separators.

    Returns:
        Canonical POSIX-style repository-relative path with no leading slash.

    Raises:
        InvalidPathError: If the path is empty, absolute, contains a ``..``
            segment, contains a NUL byte, or normalises to nothing.
    """
    if not isinstance(path, str):
        raise InvalidPathError("path must be a string", {"type": type(path).__name__})
    if not path.strip():
        raise InvalidPathError("path must not be empty", {"path": path})
    if "\x00" in path:
        raise InvalidPathError("path must not contain a NUL byte", {"path": repr(path)})

    candidate = path.replace("\\", "/").strip()
    if candidate.startswith("/"):
        raise InvalidPathError(
            "path must be relative to the repository root", {"path": path}
        )
    # Guard against Windows drive-qualified paths such as "C:/x".
    if len(candidate) >= 2 and candidate[1] == ":":
        raise InvalidPathError(
            "path must be relative to the repository root", {"path": path}
        )

    segments = [segment for segment in candidate.split("/") if segment not in ("", ".")]
    if any(segment == ".." for segment in segments):
        raise InvalidPathError("path must not contain a parent segment", {"path": path})
    if not segments:
        raise InvalidPathError(
            "path must reference a file or directory", {"path": path}
        )

    return "/".join(segments)


def parent_directory(normalised_path: str) -> str:
    """Return the parent directory of a normalised path.

    Args:
        normalised_path: Path already returned by
            :func:`normalise_repository_path`.

    Returns:
        The parent directory path, or ``""`` for a path at the repository root.
        The empty string denotes the root module, which is a valid module
        identity for a repository whose files sit at the top level.
    """
    parent = posixpath.dirname(normalised_path)
    return parent


def path_segments(normalised_path: str) -> Sequence[str]:
    """Split a normalised path into its segments.

    Args:
        normalised_path: Path already returned by
            :func:`normalise_repository_path`.
    """
    return tuple(normalised_path.split("/"))


def is_within(normalised_path: str, normalised_directory: str) -> bool:
    """Whether a path lies inside a directory.

    Args:
        normalised_path: Candidate path.
        normalised_directory: Directory path. The empty string denotes the
            repository root and therefore contains every path.

    Returns:
        ``True`` if the path is the directory itself or lies beneath it.
    """
    if normalised_directory == "":
        return True
    return normalised_path == normalised_directory or normalised_path.startswith(
        normalised_directory + "/"
    )
