"""Integration tests for the filesystem content-addressable store.

The store's guarantees are content addressing, idempotent writes, immutability and
bounded directory fan-out. Twin Spec section 6.4 rests on the first two: structural
sharing across commits is automatic only because identical content yields an
identical key and re-writing it is a no-op.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from ria.domain.errors import BlobNotFoundError
from ria.domain.identity import ContentHash
from ria.infrastructure.storage.filesystem_blob_store import FilesystemBlobStore
from ria.observability.metrics import InMemoryMetricsSink
from ria.ports.blob_store import ContentAddressableStore

PAYLOAD = b"def handler():\n    return 200\n"
OTHER = b"def other():\n    return 404\n"


@pytest.fixture
def store(tmp_path: Path, metrics: InMemoryMetricsSink) -> FilesystemBlobStore:
    """A store rooted in the test's temporary directory."""
    return FilesystemBlobStore(tmp_path / "blobs", metrics)


class TestPortConformance:
    """Structural conformance to the port."""

    def test_satisfies_the_port(self, store: FilesystemBlobStore) -> None:
        """The adapter is structurally a :class:`ContentAddressableStore`."""
        assert isinstance(store, ContentAddressableStore)


class TestWriting:
    """Storing content."""

    def test_put_returns_the_content_hash(self, store: FilesystemBlobStore) -> None:
        """The returned key is the digest of the content, not an assigned identifier."""
        assert store.put(PAYLOAD) == ContentHash.of_bytes(PAYLOAD)

    def test_put_is_idempotent(self, store: FilesystemBlobStore) -> None:
        """Re-storing existing content is a no-op returning the same key.

        Ingestion encounters the same content repeatedly across commits and
        branches; treating a repeat as an error would make every incremental build
        fail.
        """
        first = store.put(PAYLOAD)
        second = store.put(PAYLOAD)
        assert first == second
        assert store.get(first) == PAYLOAD

    def test_identical_content_is_stored_once(
        self, store: FilesystemBlobStore, tmp_path: Path
    ) -> None:
        """Deduplication is automatic, which is what makes structural sharing free."""
        store.put(PAYLOAD)
        store.put(PAYLOAD)
        files = [path for path in (tmp_path / "blobs").rglob("*") if path.is_file()]
        assert len(files) == 1

    def test_distinct_content_is_stored_separately(
        self, store: FilesystemBlobStore
    ) -> None:
        """Different content yields different keys and both are retrievable."""
        first = store.put(PAYLOAD)
        second = store.put(OTHER)
        assert first != second
        assert store.get(first) == PAYLOAD
        assert store.get(second) == OTHER

    def test_stores_empty_content(self, store: FilesystemBlobStore) -> None:
        """An empty file is valid content with a well-defined key."""
        content_hash = store.put(b"")
        assert store.exists(content_hash)
        assert store.get(content_hash) == b""

    def test_put_stream_matches_put(self, store: FilesystemBlobStore) -> None:
        """Streaming and in-memory writes produce the same key.

        Admission limits permit files that should not be held in memory alongside a
        worker pool, so the streaming path must be interchangeable.
        """
        large = b"y" * 200_000
        streamed = store.put_stream(io.BytesIO(large))
        assert streamed == ContentHash.of_bytes(large)
        assert store.get(streamed) == large

    def test_put_stream_is_idempotent(self, store: FilesystemBlobStore) -> None:
        """A repeated streaming write is also a no-op."""
        first = store.put_stream(io.BytesIO(PAYLOAD))
        second = store.put_stream(io.BytesIO(PAYLOAD))
        assert first == second


class TestReading:
    """Retrieving content."""

    def test_get_returns_exact_bytes(self, store: FilesystemBlobStore) -> None:
        """Content round-trips byte for byte, including line endings.

        Any normalisation would change the content hash of the retrieved bytes and
        break the reuse guarantee.
        """
        content_hash = store.put(PAYLOAD)
        retrieved = store.get(content_hash)
        assert retrieved == PAYLOAD
        assert ContentHash.of_bytes(retrieved) == content_hash

    def test_get_raises_for_absent_content(self, store: FilesystemBlobStore) -> None:
        """Reading an unstored key raises rather than returning empty bytes."""
        with pytest.raises(BlobNotFoundError):
            store.get(ContentHash.of_bytes(b"never stored"))

    def test_open_streams_content(self, store: FilesystemBlobStore) -> None:
        """A caller may read large content without buffering it whole."""
        content_hash = store.put(PAYLOAD)
        with store.open(content_hash) as stream:
            assert stream.read() == PAYLOAD

    def test_open_raises_for_absent_content(self, store: FilesystemBlobStore) -> None:
        """Opening an unstored key raises."""
        with pytest.raises(BlobNotFoundError):
            store.open(ContentHash.of_bytes(b"never stored"))

    def test_exists_reflects_presence(self, store: FilesystemBlobStore) -> None:
        """Presence is queryable without reading content."""
        content_hash = store.put(PAYLOAD)
        assert store.exists(content_hash) is True
        assert store.exists(ContentHash.of_bytes(b"absent")) is False

    def test_stat_reports_size(self, store: FilesystemBlobStore) -> None:
        """Metadata is available without reading the content."""
        content_hash = store.put(PAYLOAD)
        stat = store.stat(content_hash)
        assert stat is not None
        assert stat.content_hash == content_hash
        assert stat.size_bytes == len(PAYLOAD)
        assert stat.stored_at.tzinfo is not None

    def test_stat_returns_none_for_absent_content(
        self, store: FilesystemBlobStore
    ) -> None:
        """Absence is reported as ``None`` rather than raising."""
        assert store.stat(ContentHash.of_bytes(b"absent")) is None


class TestBulkPresence:
    """The bulk presence filter."""

    def test_missing_returns_only_absent_hashes(
        self, store: FilesystemBlobStore
    ) -> None:
        """Ingestion asks this once per tree rather than once per file.

        A per-hash round trip over a tree of hundreds of thousands of entries would
        dominate the incremental build budget of SDD section 6.3.
        """
        present = store.put(PAYLOAD)
        absent = ContentHash.of_bytes(b"absent")
        assert tuple(store.missing([present, absent])) == (absent,)

    def test_missing_preserves_input_order(self, store: FilesystemBlobStore) -> None:
        """Order is preserved so a caller can correlate results with its input."""
        first = ContentHash.of_bytes(b"one")
        second = ContentHash.of_bytes(b"two")
        third = ContentHash.of_bytes(b"three")
        store.put(b"two")
        assert tuple(store.missing([first, second, third])) == (first, third)

    def test_missing_handles_an_empty_input(self, store: FilesystemBlobStore) -> None:
        """An empty query returns an empty result rather than raising."""
        assert tuple(store.missing([])) == ()

    def test_missing_deduplicates_the_work_list(
        self, store: FilesystemBlobStore
    ) -> None:
        """A repeated absent hash is reported once.

        The caller's intent is a work list of content to write. Reporting one
        absent hash twice would fetch and store the same blob twice.
        """
        absent = ContentHash.of_bytes(b"absent")
        assert tuple(store.missing([absent, absent])) == (absent,)


class TestDeletion:
    """Retention enforcement."""

    def test_delete_removes_content(self, store: FilesystemBlobStore) -> None:
        """Deletion is available for retention enforcement."""
        content_hash = store.put(PAYLOAD)
        assert store.delete(content_hash) is True
        assert store.exists(content_hash) is False

    def test_delete_of_absent_content_reports_false(
        self, store: FilesystemBlobStore
    ) -> None:
        """Deleting nothing is not an error, which keeps retention jobs idempotent."""
        assert store.delete(ContentHash.of_bytes(b"absent")) is False

    def test_content_can_be_restored_after_deletion(
        self, store: FilesystemBlobStore
    ) -> None:
        """Because identity is the digest, re-storing restores the same key.

        This is why the store need not reference count: a blob deleted in error is
        recoverable from git, which SDD section 6.2 designates the system of record.
        """
        content_hash = store.put(PAYLOAD)
        store.delete(content_hash)
        assert store.put(PAYLOAD) == content_hash


class TestLayout:
    """On-disk structure."""

    def test_shards_the_digest_into_nested_directories(
        self, tmp_path: Path, metrics: InMemoryMetricsSink
    ) -> None:
        """Sharding bounds directory fan-out for large monorepos."""
        store = FilesystemBlobStore(tmp_path / "blobs", metrics)
        content_hash = store.put(PAYLOAD)
        expected = (tmp_path / "blobs") / Path(content_hash.shard_path())
        assert expected.is_file()

    def test_shard_geometry_is_configurable(
        self, tmp_path: Path, metrics: InMemoryMetricsSink
    ) -> None:
        """Geometry follows the storage settings rather than being fixed."""
        store = FilesystemBlobStore(
            tmp_path / "blobs", metrics, shard_depth=1, shard_width=3
        )
        content_hash = store.put(PAYLOAD)
        expected = (tmp_path / "blobs") / Path(
            content_hash.shard_path(depth=1, width=3)
        )
        assert expected.is_file()

    def test_creates_its_root_on_demand(
        self, tmp_path: Path, metrics: InMemoryMetricsSink
    ) -> None:
        """The store root need not exist before first use."""
        root = tmp_path / "deeply" / "nested" / "blobs"
        store = FilesystemBlobStore(root, metrics)
        store.put(PAYLOAD)
        assert root.is_dir()

    def test_two_stores_over_one_root_share_content(
        self, tmp_path: Path, metrics: InMemoryMetricsSink
    ) -> None:
        """Content written by one process is visible to another.

        The ingestion worker pool writes to one store from many processes, so
        visibility across instances is a requirement, not an accident.
        """
        first = FilesystemBlobStore(tmp_path / "blobs", metrics)
        second = FilesystemBlobStore(tmp_path / "blobs", metrics)
        content_hash = first.put(PAYLOAD)
        assert second.get(content_hash) == PAYLOAD
