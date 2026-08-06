"""Content-addressable storage port.

Implements the blob store of SDD section 6.2: an immutable, content-addressed
store where identity is the digest of the content itself.

Why content addressing is the enabling decision
-----------------------------------------------
Twin Spec section 6.4 states that structural sharing reduces per-commit storage
roughly six-hundredfold and that "without this, commit-addressing is economically
impossible". A content-addressed store is what makes sharing automatic rather
than something the caller must arrange: a file unchanged across five hundred
commits is stored once because its digest is unchanged, with no reference
counting, no diffing and no coordination.

Consequences for implementations
--------------------------------
* :meth:`ContentAddressableStore.put` is idempotent. Writing content that already
  exists is a no-op returning the same hash, never an error.
* Content is immutable. There is no update operation, because changing the bytes
  under a hash would falsify every fact derived from that hash.
* :meth:`ContentAddressableStore.delete` exists for retention enforcement only.
  It is unsafe to call while any commit still references the blob, and callers are
  responsible for that determination; the store deliberately does not reference
  count, because doing so would make every write transactional and destroy the
  write throughput the ingestion pipeline depends on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import IO, Iterable, Optional, Protocol, runtime_checkable

from ria.domain.identity import ContentHash

__all__ = ["BlobStat", "ContentAddressableStore"]


@dataclass(frozen=True)
class BlobStat:
    """Metadata about a stored blob.

    Attributes:
        content_hash: Identity of the blob.
        size_bytes: Size of the stored content.
        stored_at: When the blob was first written.
    """

    content_hash: ContentHash
    size_bytes: int
    stored_at: datetime


@runtime_checkable
class ContentAddressableStore(Protocol):
    """Immutable store keyed by the digest of its contents.

    Implementations must be safe for concurrent use by multiple processes, because
    the ingestion worker pool of SDD section 6.3 writes to one store from many
    workers and two workers frequently encounter the same content simultaneously.
    """

    def put(self, data: bytes) -> ContentHash:
        """Store content and return its identity.

        Idempotent: storing content that is already present returns the existing
        hash without rewriting.

        Args:
            data: Content to store.

        Returns:
            The content hash under which the content is stored.

        Raises:
            StorageError: If the content could not be written durably.
        """
        ...

    def put_stream(self, stream: IO[bytes]) -> ContentHash:
        """Store content read from a stream without buffering it whole.

        Required because admission limits permit files of a size that should not
        be held in memory alongside a worker pool.

        Args:
            stream: Readable binary stream positioned at the start of the content.

        Returns:
            The content hash under which the content is stored.

        Raises:
            StorageError: If the content could not be written durably.
        """
        ...

    def get(self, content_hash: ContentHash) -> bytes:
        """Read stored content in full.

        Args:
            content_hash: Identity of the content.

        Returns:
            The stored bytes.

        Raises:
            BlobNotFoundError: If no content is stored under the hash.
            StorageError: If the content exists but could not be read.
        """
        ...

    def open(self, content_hash: ContentHash) -> IO[bytes]:
        """Open stored content as a readable binary stream.

        The caller owns the returned stream and must close it.

        Args:
            content_hash: Identity of the content.

        Returns:
            A readable binary stream.

        Raises:
            BlobNotFoundError: If no content is stored under the hash.
        """
        ...

    def exists(self, content_hash: ContentHash) -> bool:
        """Whether content is stored under a hash.

        Args:
            content_hash: Identity to test.
        """
        ...

    def stat(self, content_hash: ContentHash) -> Optional[BlobStat]:
        """Return metadata about stored content.

        Args:
            content_hash: Identity of the content.

        Returns:
            The metadata, or ``None`` if the content is absent.
        """
        ...

    def missing(self, hashes: Iterable[ContentHash]) -> Iterable[ContentHash]:
        """Filter a set of hashes down to those not yet stored.

        Exists as a bulk operation because ingestion asks this question once per
        file across trees of hundreds of thousands of entries, and a per-hash
        round trip would dominate the ingestion budget of SDD section 6.3.

        The result is deduplicated: the caller's intent is a work list of content
        to write, and reporting one absent hash twice would cause the same blob to
        be fetched and stored twice.

        Args:
            hashes: Candidate identities. Duplicates are permitted.

        Returns:
            The distinct identities that are absent from the store, in the order of
            their first appearance in the input.
        """
        ...

    def delete(self, content_hash: ContentHash) -> bool:
        """Remove stored content.

        For retention enforcement only. The store does not reference count, so the
        caller must have established that no commit references the blob.

        Args:
            content_hash: Identity of the content to remove.

        Returns:
            ``True`` if content was removed, ``False`` if it was already absent.
        """
        ...
