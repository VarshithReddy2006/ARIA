"""Tests for the identity value objects.

Twin Spec section 3.1 gives identity precedence over everything else in the
specification, so these are the tests that matter most: a moniker that validates
loosely, or a content hash that accepts a malformed value, corrupts every join and
every historical trace built on top of it.
"""

from __future__ import annotations

import io
import uuid

import pytest

from ria.domain.errors import (
    InvalidCommitShaError,
    InvalidContentHashError,
    InvalidMonikerError,
)
from ria.domain.identity import (
    LOCAL_PACKAGE,
    CommitId,
    CommitSha,
    ContentHash,
    Moniker,
    MonikerScheme,
    RepositoryId,
)

_SHA1 = "a" * 40
_SHA256 = "b" * 64


class TestMoniker:
    """Grammar and construction of :class:`~ria.domain.identity.Moniker`."""

    @pytest.mark.parametrize(
        "value,scheme,package,descriptor",
        [
            ("repo:github.com:owner/name", "repo", "github.com", "owner/name"),
            ("file:.:src/handlers/auth.py", "file", ".", "src/handlers/auth.py"),
            ("module:.:src/handlers", "module", ".", "src/handlers"),
            (
                "python:mypkg:module/Class#method().",
                "python",
                "mypkg",
                "module/Class#method().",
            ),
            (
                "typescript:@scope/pkg:src/mod/Class#method().",
                "typescript",
                "@scope/pkg",
                "src/mod/Class#method().",
            ),
        ],
    )
    def test_parses_every_documented_form(
        self, value: str, scheme: str, package: str, descriptor: str
    ) -> None:
        """Each example from Twin Spec section 3.1 round-trips through parsing."""
        moniker = Moniker.parse(value)
        assert (moniker.scheme, moniker.package, moniker.descriptor) == (
            scheme,
            package,
            descriptor,
        )
        assert str(moniker) == value

    def test_descriptor_may_contain_colons(self) -> None:
        """Only the first two separators split, so a descriptor keeps its colons.

        Language schemes embed type signatures that contain colons, so a splitter
        that consumed every separator would truncate a valid moniker.
        """
        moniker = Moniker.parse("java:com.example:pkg/Class#method(a:b)")
        assert moniker.descriptor == "pkg/Class#method(a:b)"

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "repo",
            "repo:github.com",
            ":github.com:owner/name",
            "repo::owner/name",
            "repo:github.com:",
            "repo :github.com:owner/name",
            "repo:git hub.com:owner/name",
        ],
    )
    def test_rejects_malformed_values(self, value: str) -> None:
        """A moniker missing a component or containing whitespace is rejected."""
        with pytest.raises(InvalidMonikerError):
            Moniker.parse(value)

    def test_rejects_non_string(self) -> None:
        """A non-string input is rejected rather than coerced."""
        with pytest.raises(InvalidMonikerError):
            Moniker.parse(None)  # type: ignore[arg-type]

    def test_rejects_descriptor_with_surrounding_whitespace(self) -> None:
        """Whitespace around a descriptor would create two identities for one entity."""
        with pytest.raises(InvalidMonikerError):
            Moniker(scheme="file", package=".", descriptor=" src/a.py ")

    def test_repository_factory(self) -> None:
        """The repository factory produces the documented ``repo:host:owner/name``."""
        moniker = Moniker.for_repository(
            host="github.com", owner="acme", name="widgets"
        )
        assert str(moniker) == "repo:github.com:acme/widgets"
        assert moniker.scheme == MonikerScheme.REPOSITORY
        assert not moniker.is_local

    def test_file_and_module_factories_are_local(self) -> None:
        """File and module monikers use the local package sentinel."""
        assert Moniker.for_file("src/a.py").package == LOCAL_PACKAGE
        assert Moniker.for_module("src").is_local

    def test_is_hashable_and_comparable(self) -> None:
        """Monikers are usable as dictionary keys, which every index relies on."""
        first = Moniker.parse("file:.:src/a.py")
        second = Moniker.parse("file:.:src/a.py")
        assert first == second
        assert len({first, second}) == 1


class TestRepositoryId:
    """Construction of :class:`~ria.domain.identity.RepositoryId`."""

    def test_generate_is_unique(self) -> None:
        """Generated identifiers do not collide."""
        assert RepositoryId.generate() != RepositoryId.generate()

    def test_round_trips_through_string(self) -> None:
        """An identifier survives serialisation to text and back."""
        original = RepositoryId.generate()
        assert RepositoryId.parse(str(original)) == original

    def test_rejects_non_uuid(self) -> None:
        """A malformed identifier is rejected."""
        with pytest.raises(ValueError):
            RepositoryId.parse("not-a-uuid")

    def test_wraps_a_uuid(self) -> None:
        """The identifier is a thin wrapper over a UUID value."""
        value = uuid.uuid4()
        assert RepositoryId(value).value == value


class TestCommitSha:
    """Validation of :class:`~ria.domain.identity.CommitSha`."""

    @pytest.mark.parametrize("value", [_SHA1, _SHA256])
    def test_accepts_sha1_and_sha256_lengths(self, value: str) -> None:
        """Both git object name lengths are representable."""
        assert CommitSha(value).value == value

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "abc",
            "A" * 40,
            "g" * 40,
            "a" * 39,
            "a" * 41,
            "a" * 63,
        ],
    )
    def test_rejects_anything_that_is_not_a_full_object_name(self, value: str) -> None:
        """Abbreviated, uppercase and non-hexadecimal values are rejected.

        Only complete object names are representable, so an ambiguous identity can
        never be persisted; abbreviations are expanded by the git adapter first.
        """
        with pytest.raises(InvalidCommitShaError):
            CommitSha(value)

    def test_rejects_non_string(self) -> None:
        """A non-string input is rejected rather than coerced."""
        with pytest.raises(InvalidCommitShaError):
            CommitSha(12345)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("abcdef1", True),
            ("abcdef", False),
            (_SHA1, True),
            ("z" * 10, False),
            ("a" * 65, False),
        ],
    )
    def test_is_probable_sha_recognises_abbreviations(
        self, value: str, expected: bool
    ) -> None:
        """Ref resolution uses this to decide whether to try ``rev-parse`` first."""
        assert CommitSha.is_probable_sha(value) is expected

    def test_short_form_is_twelve_characters(self) -> None:
        """The short form is for display only and has a fixed length."""
        assert CommitSha(_SHA1).short == "a" * 12


class TestCommitId:
    """Composite key behaviour of :class:`~ria.domain.identity.CommitId`."""

    def test_combines_repository_and_sha(self) -> None:
        """The key renders as ``repository:sha`` and compares by both components."""
        repository_id = RepositoryId.generate()
        key = CommitId(repository_id=repository_id, sha=CommitSha(_SHA1))
        assert str(key) == f"{repository_id}:{_SHA1}"

    def test_same_sha_in_two_repositories_are_distinct(self) -> None:
        """Identical content in two repositories yields distinct commit keys.

        This is why the key is a type rather than a bare SHA: forks share object
        names, and conflating them would merge two repositories' histories.
        """
        sha = CommitSha(_SHA1)
        first = CommitId(repository_id=RepositoryId.generate(), sha=sha)
        second = CommitId(repository_id=RepositoryId.generate(), sha=sha)
        assert first != second


class TestContentHash:
    """Validation and derivation of :class:`~ria.domain.identity.ContentHash`."""

    def test_of_bytes_is_deterministic(self) -> None:
        """Identical content yields an identical hash, which is what enables reuse."""
        assert ContentHash.of_bytes(b"payload") == ContentHash.of_bytes(b"payload")

    def test_different_content_yields_different_hash(self) -> None:
        """Distinct content is distinguishable."""
        assert ContentHash.of_bytes(b"a") != ContentHash.of_bytes(b"b")

    def test_of_stream_matches_of_bytes(self) -> None:
        """Streaming and in-memory digests agree, so large files may bypass memory."""
        payload = b"x" * 5000
        streamed = ContentHash.of_stream(io.BytesIO(payload), chunk_size=64)
        assert streamed == ContentHash.of_bytes(payload)

    def test_of_empty_stream_is_valid(self) -> None:
        """An empty file has a well-defined hash rather than being an error."""
        assert ContentHash.of_stream(io.BytesIO(b"")) == ContentHash.of_bytes(b"")

    def test_canonical_form_carries_the_algorithm(self) -> None:
        """The algorithm prefix is part of the value, not implied."""
        content_hash = ContentHash.of_bytes(b"payload")
        assert str(content_hash).startswith("sha256:")
        assert len(content_hash.digest) == 64

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "deadbeef",
            "sha1:" + "a" * 40,
            "sha256:" + "a" * 63,
            "sha256:" + "A" * 64,
            "sha256:" + "z" * 64,
            "a" * 64,
        ],
    )
    def test_rejects_malformed_values(self, value: str) -> None:
        """A hash without the expected prefix and digest length is rejected."""
        with pytest.raises(InvalidContentHashError):
            ContentHash(value)

    def test_rejects_non_string(self) -> None:
        """A non-string input is rejected rather than coerced."""
        with pytest.raises(InvalidContentHashError):
            ContentHash(b"sha256:")  # type: ignore[arg-type]

    def test_shard_path_bounds_directory_fan_out(self) -> None:
        """Sharding nests the digest so no directory holds every blob."""
        content_hash = ContentHash.of_bytes(b"payload")
        digest = content_hash.digest
        assert content_hash.shard_path() == f"{digest[:2]}/{digest[2:4]}/{digest}"

    def test_shard_path_honours_depth_and_width(self) -> None:
        """Shard geometry is configurable, matching the storage settings."""
        content_hash = ContentHash.of_bytes(b"payload")
        digest = content_hash.digest
        assert content_hash.shard_path(depth=1, width=3) == f"{digest[:3]}/{digest}"
        assert content_hash.shard_path(depth=0) == digest

    @pytest.mark.parametrize("depth,width", [(-1, 2), (2, 0)])
    def test_shard_path_rejects_invalid_geometry(self, depth: int, width: int) -> None:
        """Nonsensical shard geometry is rejected rather than producing odd paths."""
        with pytest.raises(ValueError):
            ContentHash.of_bytes(b"payload").shard_path(depth=depth, width=width)
