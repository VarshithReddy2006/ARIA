"""Tests for repository-relative path normalisation.

One path must be represented by exactly one string everywhere in the system. If
``src/a.py``, ``./src/a.py`` and ``src\\a.py`` can all reach storage, they become
three identities for one file and every join silently under-matches — a failure that
produces plausible but incomplete answers rather than an error.
"""

from __future__ import annotations

import pytest

from ria.domain.errors import InvalidPathError
from ria.domain.paths import (
    is_within,
    normalise_repository_path,
    parent_directory,
    path_segments,
)


class TestNormalisation:
    """Behaviour of :func:`~ria.domain.paths.normalise_repository_path`."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("src/a.py", "src/a.py"),
            ("./src/a.py", "src/a.py"),
            ("src//a.py", "src/a.py"),
            ("src\\a.py", "src/a.py"),
            (".\\src\\\\deep\\a.py", "src/deep/a.py"),
            ("  src/a.py  ", "src/a.py"),
            ("a.py", "a.py"),
            ("src/./a.py", "src/a.py"),
            ("src/deep/", "src/deep"),
        ],
    )
    def test_produces_one_canonical_form(self, raw: str, expected: str) -> None:
        """Every spelling of a path collapses to a single canonical string."""
        assert normalise_repository_path(raw) == expected

    def test_is_idempotent(self) -> None:
        """Normalising an already-normalised path changes nothing.

        Idempotence matters because entities normalise on construction and are then
        reconstructed from storage; a non-idempotent function would drift a path on
        every round trip.
        """
        once = normalise_repository_path("./src\\a.py")
        assert normalise_repository_path(once) == once

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "/etc/passwd", "/src/a.py", "C:/Windows/x", "c:/x"],
    )
    def test_rejects_absolute_paths(self, raw: str) -> None:
        """Absolute and drive-qualified paths are rejected; paths are relative."""
        with pytest.raises(InvalidPathError):
            normalise_repository_path(raw)

    @pytest.mark.parametrize(
        "raw",
        ["../secrets", "src/../../etc", "src/..", "..\\x"],
    )
    def test_rejects_parent_segments_rather_than_resolving_them(self, raw: str) -> None:
        """A ``..`` segment is refused, never resolved.

        Resolving would silently accept a path that escapes the repository root.
        This is a containment concern, so the correct response is refusal.
        """
        with pytest.raises(InvalidPathError):
            normalise_repository_path(raw)

    def test_rejects_nul_byte(self) -> None:
        """A NUL byte cannot appear in a stored path."""
        with pytest.raises(InvalidPathError):
            normalise_repository_path("src/a\x00.py")

    def test_rejects_path_that_normalises_to_nothing(self) -> None:
        """A path consisting only of separators and dots references no entity."""
        with pytest.raises(InvalidPathError):
            normalise_repository_path("./")

    def test_rejects_non_string(self) -> None:
        """A non-string input is rejected rather than coerced."""
        with pytest.raises(InvalidPathError):
            normalise_repository_path(None)  # type: ignore[arg-type]


class TestDerivations:
    """Behaviour of the derived path helpers."""

    @pytest.mark.parametrize(
        "path,expected",
        [("src/deep/a.py", "src/deep"), ("src/a.py", "src"), ("a.py", "")],
    )
    def test_parent_directory(self, path: str, expected: str) -> None:
        """The parent of a root-level file is the empty root module path."""
        assert parent_directory(path) == expected

    def test_path_segments(self) -> None:
        """Segments are returned in order as an immutable tuple."""
        assert path_segments("src/deep/a.py") == ("src", "deep", "a.py")

    @pytest.mark.parametrize(
        "path,directory,expected",
        [
            ("src/a.py", "src", True),
            ("src/deep/a.py", "src", True),
            ("src/a.py", "", True),
            ("srcx/a.py", "src", False),
            ("src", "src", True),
            ("other/a.py", "src", False),
        ],
    )
    def test_is_within(self, path: str, directory: str, expected: bool) -> None:
        """Containment is by path segment, so ``srcx`` is not inside ``src``.

        A naive prefix test would report ``srcx/a.py`` as inside ``src``, which
        would attribute one module's files to another in every module-scoped metric.
        """
        assert is_within(path, directory) is expected
