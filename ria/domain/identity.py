"""Identity value objects.

Twin Spec section 3.1 states that nothing in the specification matters more than
identity, and fixes three rules:

Rule 1
    Structural entities are identified by *moniker*, never by path. Monikers
    survive file moves, which is what makes the History facet possible at all.
Rule 2
    Every fact is keyed by ``(repo_id, commit_id, moniker)``. There are no
    unversioned facts.
Rule 3
    Content identity (:class:`ContentHash`) is separate from logical identity
    (:class:`Moniker`). Monikers give historical continuity; content hashes give
    computational reuse. Conflating them loses one capability or the other.

Every type in this module is an immutable value object with validation at
construction. An invalid identity cannot be represented.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import IO

from ria.domain.errors import (
    InvalidCommitShaError,
    InvalidContentHashError,
    InvalidMonikerError,
)

__all__ = [
    "MonikerScheme",
    "Moniker",
    "RepositoryId",
    "CommitSha",
    "CommitId",
    "ContentHash",
    "LOCAL_PACKAGE",
]

#: Package component used for entities local to the repository under analysis,
#: as shown throughout the moniker examples of Twin Spec section 3.1.
LOCAL_PACKAGE = "."

_MONIKER_COMPONENT = re.compile(r"^[^:\s]+$")
_SHA_PATTERN = re.compile(r"^[0-9a-f]+$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

#: Git object name lengths: SHA-1 repositories and SHA-256 repositories.
_VALID_SHA_LENGTHS = (40, 64)

#: Minimum length accepted for an abbreviated SHA supplied by a human.
_MIN_ABBREV_SHA = 7


class MonikerScheme:
    """Well-known moniker schemes.

    Not an :class:`~enum.Enum`: the scheme space is deliberately open because
    each language plugin contributes its own scheme (Twin Spec section 10, "New
    entities, kinds, and fields are additive"). These constants name the schemes
    the core owns.
    """

    REPOSITORY = "repo"
    FILE = "file"
    MODULE = "module"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"


@dataclass(frozen=True)
class Moniker:
    """Stable, scheme-qualified logical identity.

    Grammar, from Twin Spec section 3.1::

        scheme:package:descriptor

        python:mypkg:module/Class#method().
        typescript:@scope/pkg:src/mod/Class#method().
        file:.:src/handlers/auth.py
        module:.:src/handlers
        repo:github.com:owner/name

    ``scheme`` and ``package`` may not contain a colon or whitespace;
    ``descriptor`` may contain colons, so parsing splits on the first two
    separators only.

    Attributes:
        scheme: Namespace of the identity, typically a language or entity kind.
        package: Distribution or host qualifier. :data:`LOCAL_PACKAGE` for
            entities local to the repository under analysis.
        descriptor: Scheme-specific remainder identifying the entity.
    """

    scheme: str
    package: str
    descriptor: str

    def __post_init__(self) -> None:
        for name, value in (
            ("scheme", self.scheme),
            ("package", self.package),
        ):
            if not value or not _MONIKER_COMPONENT.match(value):
                raise InvalidMonikerError(
                    f"moniker {name} must be non-empty and contain no colon or whitespace",
                    {name: value},
                )
        if not self.descriptor or self.descriptor.strip() != self.descriptor:
            raise InvalidMonikerError(
                "moniker descriptor must be non-empty and free of surrounding whitespace",
                {"descriptor": self.descriptor},
            )

    @classmethod
    def parse(cls, value: str) -> "Moniker":
        """Parse a moniker from its canonical string form.

        Args:
            value: Canonical ``scheme:package:descriptor`` string.

        Returns:
            The parsed moniker.

        Raises:
            InvalidMonikerError: If the string does not have three components or
                any component is invalid.
        """
        if not isinstance(value, str):
            raise InvalidMonikerError(
                "moniker must be a string", {"type": type(value).__name__}
            )
        parts = value.split(":", 2)
        if len(parts) != 3:
            raise InvalidMonikerError(
                "moniker must have the form scheme:package:descriptor",
                {"value": value},
            )
        return cls(scheme=parts[0], package=parts[1], descriptor=parts[2])

    @classmethod
    def for_repository(cls, host: str, owner: str, name: str) -> "Moniker":
        """Build the moniker of a repository, for example ``repo:github.com:owner/name``.

        Args:
            host: Forge hostname, for example ``github.com``.
            owner: Owning user or organisation.
            name: Repository name.
        """
        return cls(
            scheme=MonikerScheme.REPOSITORY, package=host, descriptor=f"{owner}/{name}"
        )

    @classmethod
    def for_file(cls, normalised_path: str) -> "Moniker":
        """Build the moniker of a file unit from an already-normalised path.

        Args:
            normalised_path: Repository-relative path produced by
                :func:`ria.domain.paths.normalise_repository_path`.
        """
        return cls(
            scheme=MonikerScheme.FILE, package=LOCAL_PACKAGE, descriptor=normalised_path
        )

    @classmethod
    def for_module(cls, normalised_path: str) -> "Moniker":
        """Build the moniker of a module from an already-normalised path.

        Args:
            normalised_path: Repository-relative directory path.
        """
        return cls(
            scheme=MonikerScheme.MODULE,
            package=LOCAL_PACKAGE,
            descriptor=normalised_path,
        )

    @property
    def is_local(self) -> bool:
        """Whether the moniker refers to an entity inside the analysed repository."""
        return self.package == LOCAL_PACKAGE

    def __str__(self) -> str:
        return f"{self.scheme}:{self.package}:{self.descriptor}"


@dataclass(frozen=True)
class RepositoryId:
    """Internal stable identifier of a repository.

    Distinct from :class:`Moniker` on purpose. The moniker derives from the
    origin URL and can therefore change when a repository is renamed or moved
    between owners; the identifier never changes, so foreign keys remain valid
    across such events.
    """

    value: uuid.UUID

    @classmethod
    def generate(cls) -> "RepositoryId":
        """Create a fresh random identifier."""
        return cls(uuid.uuid4())

    @classmethod
    def parse(cls, value: str) -> "RepositoryId":
        """Parse an identifier from its canonical string form.

        Args:
            value: UUID string.

        Raises:
            ValueError: If the value is not a valid UUID.
        """
        return cls(uuid.UUID(value))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class CommitSha:
    """A full git object name.

    Only complete object names are representable. Abbreviated SHAs supplied by
    humans must be expanded by the git adapter before entering the domain, so
    that no ambiguous identity is ever persisted.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidCommitShaError(
                "commit sha must be a string", {"type": type(self.value).__name__}
            )
        if len(self.value) not in _VALID_SHA_LENGTHS or not _SHA_PATTERN.match(
            self.value
        ):
            raise InvalidCommitShaError(
                "commit sha must be 40 or 64 lowercase hexadecimal characters",
                {"value": self.value, "length": len(self.value)},
            )

    @staticmethod
    def is_probable_sha(value: str) -> bool:
        """Whether a user-supplied string looks like a full or abbreviated SHA.

        Used by ref resolution to decide whether to try ``rev-parse`` on the
        value directly before treating it as a symbolic ref.

        Args:
            value: Candidate string.
        """
        return (
            isinstance(value, str)
            and _MIN_ABBREV_SHA <= len(value) <= 64
            and bool(_SHA_PATTERN.match(value))
        )

    @property
    def short(self) -> str:
        """First twelve characters, for log and display use only."""
        return self.value[:12]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CommitId:
    """Composite primary key of a commit.

    Implements the ``(repo_id, sha)`` key of Twin Spec section 3.2. Present as a
    type rather than a tuple so that a repository identifier and a commit SHA
    cannot be transposed at a call site.
    """

    repository_id: RepositoryId
    sha: CommitSha

    def __str__(self) -> str:
        return f"{self.repository_id}:{self.sha}"


@dataclass(frozen=True)
class ContentHash:
    """Physical identity of a byte sequence.

    Canonical form is ``sha256:<64 lowercase hex>``. The algorithm prefix is part
    of the value so that a future migration to a different digest is
    distinguishable in stored data rather than silently ambiguous.

    Per Twin Spec section 6.4 this is the cache key that makes incremental
    indexing nearly free: a file whose content hash is unchanged is never
    reparsed, in any commit or branch.
    """

    value: str

    #: Digest algorithm currently produced by this class.
    ALGORITHM = "sha256"

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidContentHashError(
                "content hash must be a string", {"type": type(self.value).__name__}
            )
        prefix, _, digest = self.value.partition(":")
        if prefix != self.ALGORITHM or not _SHA256_HEX.match(digest):
            raise InvalidContentHashError(
                "content hash must have the form sha256:<64 lowercase hex>",
                {"value": self.value},
            )

    @classmethod
    def of_bytes(cls, data: bytes) -> "ContentHash":
        """Compute the content hash of an in-memory byte sequence.

        Args:
            data: Bytes to digest.
        """
        return cls(f"{cls.ALGORITHM}:{hashlib.sha256(data).hexdigest()}")

    @classmethod
    def of_stream(
        cls, stream: IO[bytes], chunk_size: int = 1024 * 1024
    ) -> "ContentHash":
        """Compute the content hash of a binary stream without buffering it whole.

        Args:
            stream: Readable binary stream, positioned at the start of the
                content to digest.
            chunk_size: Read granularity in bytes.

        Returns:
            The content hash of everything read from the stream.
        """
        digest = hashlib.sha256()
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
        return cls(f"{cls.ALGORITHM}:{digest.hexdigest()}")

    @property
    def digest(self) -> str:
        """Hexadecimal digest without the algorithm prefix."""
        return self.value.split(":", 1)[1]

    def shard_path(self, depth: int = 2, width: int = 2) -> str:
        """Build a sharded relative path for filesystem storage.

        Sharding keeps directory fan-out bounded, which matters because a large
        monorepo contributes hundreds of thousands of distinct blobs.

        Args:
            depth: Number of nested shard directories.
            width: Characters consumed per shard directory.

        Returns:
            A POSIX-style relative path, for example ``ab/cd/<digest>``.
        """
        if depth < 0 or width < 1:
            raise ValueError("depth must be non-negative and width must be positive")
        digest = self.digest
        segments = [
            digest[index * width : (index + 1) * width] for index in range(depth)
        ]
        segments.append(digest)
        return "/".join(segments)

    def __str__(self) -> str:
        return self.value
