"""Unit and regression tests for bounded outer batching in EmbeddingService."""

import logging
from unittest.mock import MagicMock, patch
import numpy as np

from services.embedding_service import EmbeddingService


def test_embedding_multiple_outer_batches_and_persistence(caplog):
    """Verify that multiple outer batches are used and persistence is deferred to one bulk write."""
    from services.embedding_service import _clear_l1_cache

    _clear_l1_cache()
    service = EmbeddingService(
        model_name="test-model", max_outer_batch_size=2, encode_batch_size=2
    )

    mock_model = MagicMock()
    # 5 unique items split across 3 batches (2, 2, 1)
    mock_model.encode.side_effect = [
        np.array([[0.1] * 384, [0.2] * 384]),
        np.array([[0.3] * 384, [0.4] * 384]),
        np.array([[0.5] * 384]),
    ]

    saved_batches = []

    def fake_save_cache(records):
        saved_batches.append(records)

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch(
            "services.embedding_service._save_embeddings_to_cache_bulk",
            side_effect=fake_save_cache,
        ),
        caplog.at_level(logging.INFO),
    ):
        texts = ["text_1", "text_2", "text_3", "text_4", "text_5"]
        embeddings = service.generate_embeddings_batch(texts)

        # 1. Assert model.encode was called 3 times (bounded batches)
        assert mock_model.encode.call_count == 3

        # 2. Check each batch size passed to encode
        calls = mock_model.encode.call_args_list
        assert len(calls[0][0][0]) == 2
        assert len(calls[1][0][0]) == 2
        assert len(calls[2][0][0]) == 1

        # 3. Assert deferred bulk persistence: single write with all 5 records
        assert len(saved_batches) == 1
        assert len(saved_batches[0]) == 5

        # 4. Assert ordering is preserved
        assert len(embeddings) == 5
        assert embeddings[0] == [0.1] * 384
        assert embeddings[1] == [0.2] * 384
        assert embeddings[2] == [0.3] * 384
        assert embeddings[3] == [0.4] * 384
        assert embeddings[4] == [0.5] * 384

        # 5. Assert progress logging
        assert "BGE encode progress batch=1/3 items=2 completed=2/5" in caplog.text
        assert "BGE encode progress batch=2/3 items=2 completed=4/5" in caplog.text
        assert "BGE encode progress batch=3/3 items=1 completed=5/5" in caplog.text


def test_embedding_deduplication_and_order_across_batches():
    """Verify duplicate items across batches are deduplicated and mapped back in exact original order."""
    service = EmbeddingService(model_name="test-model", max_outer_batch_size=2)

    mock_model = MagicMock()
    # 3 unique items ("A", "B", "C") -> 2 batches (2, 1)
    mock_model.encode.side_effect = [
        np.array([[1.0] * 384, [2.0] * 384]),
        np.array([[3.0] * 384]),
    ]

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
    ):
        # Input with duplicates interleaved
        texts = ["A", "B", "A", "C", "B", "A"]
        embeddings = service.generate_embeddings_batch(texts)

        # model.encode should only receive the 3 unique items across 2 batches
        assert mock_model.encode.call_count == 2
        assert mock_model.encode.call_args_list[0][0][0] == [
            "Represent this sentence: A",
            "Represent this sentence: B",
        ]
        assert mock_model.encode.call_args_list[1][0][0] == [
            "Represent this sentence: C",
        ]

        # Results must match exact input positions
        assert len(embeddings) == 6
        assert embeddings[0] == [1.0] * 384
        assert embeddings[1] == [2.0] * 384
        assert embeddings[2] == [1.0] * 384
        assert embeddings[3] == [3.0] * 384
        assert embeddings[4] == [2.0] * 384
        assert embeddings[5] == [1.0] * 384


def test_stream_generate_embeddings_batches():
    """Verify that stream_generate_embeddings_batches yields chunks and embeddings in bounded slices."""
    service = EmbeddingService(model_name="test-model", max_outer_batch_size=2)

    mock_model = MagicMock()
    mock_model.encode.side_effect = [
        np.array([[0.1] * 384, [0.2] * 384]),
        np.array([[0.3] * 384]),
    ]

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
    ):
        chunks = [
            {"path": "file1.py", "content": "def func1(): pass"},
            {"path": "file2.py", "content": "def func2(): pass"},
            {"path": "file3.py", "content": "def func3(): pass"},
        ]

        batches = list(service.stream_generate_embeddings_batches(chunks, batch_size=2))

        assert len(batches) == 2

        # Batch 1
        chunk_b1, emb_b1 = batches[0]
        assert len(chunk_b1) == 2
        assert len(emb_b1) == 2
        assert emb_b1[0] == [0.1] * 384
        assert emb_b1[1] == [0.2] * 384

        # Batch 2
        chunk_b2, emb_b2 = batches[1]
        assert len(chunk_b2) == 1
        assert len(emb_b2) == 1
        assert emb_b2[0] == [0.3] * 384


def test_qdrant_store_streaming_lifecycle():
    """Verify stage_repository_batch, publish_repository_version, and rollback_staged_version on QdrantStore."""
    from memory.qdrant_store import QdrantStore

    with (
        patch("memory.qdrant_store.QdrantClient"),
        patch("memory.qdrant_store.models"),
        patch("memory.qdrant_store.Filter"),
        patch("memory.qdrant_store.FieldCondition"),
        patch("memory.qdrant_store.MatchValue"),
    ):
        store = QdrantStore(persist_directory=":memory:")
        mock_client = MagicMock()
        store.client = mock_client
        store._active_version = MagicMock(return_value="old_ver")

        chunks_b1 = [
            {"path": "main.py", "content": "print('hello')", "chunk_id": 0},
            {"path": "main.py", "content": "print('world')", "chunk_id": 1},
        ]
        embs_b1 = [[0.1] * 384, [0.2] * 384]

        version = "ver_123"
        with patch.object(store, "add_code_chunks_bulk") as mock_add:
            staged = store.stage_repository_batch(
                "owner/repo", version, chunks_b1, embs_b1, start_chunk_id=0
            )
            assert staged == 2
            mock_add.assert_called_once()

        with patch.object(store, "_publish_version") as mock_pub:
            store.publish_repository_version("owner/repo", version)
            mock_pub.assert_called_once_with("owner/repo", version)
            mock_client.delete.assert_called_once()

        # Rollback
        store.rollback_staged_version("owner/repo", version)
        assert mock_client.delete.call_count == 2


def test_chroma_store_streaming_lifecycle():
    """Verify stage_repository_batch, publish_repository_version, and rollback_staged_version on ChromaStore."""
    from memory.chroma_store import ChromaStore

    store = ChromaStore(persist_directory="data/test_chroma_streaming")
    store.collection = MagicMock()
    store._versions = MagicMock()
    store._active_version = MagicMock(return_value="old_ver")

    chunks_b1 = [
        {"path": "main.py", "content": "print('hello')", "chunk_id": 0},
    ]
    embs_b1 = [[0.1] * 384]

    version = "ver_abc"
    with patch.object(store, "_add_in_batches") as mock_add:
        staged = store.stage_repository_batch("owner/repo", version, chunks_b1, embs_b1)
        assert staged == 1
        mock_add.assert_called_once()

    with patch.object(store, "_publish_version") as mock_pub:
        store.publish_repository_version("owner/repo", version)
        mock_pub.assert_called_once_with("owner/repo", version)
        store.collection.delete.assert_called_once()

    # Rollback
    store.rollback_staged_version("owner/repo", version)
    assert store.collection.delete.call_count == 2


def test_embedding_cache_hits_avoid_re_encoding():
    """Verify cached items are not sent to model.encode and are seamlessly merged."""
    service = EmbeddingService(model_name="test-model", max_outer_batch_size=2)

    from services.embedding_service import compute_chunk_hash, _clear_l1_cache

    _clear_l1_cache()
    hash_a = compute_chunk_hash("Represent this sentence: A", "test-model", "1.5")
    cached_map = {hash_a: [9.9] * 384}

    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[2.0] * 384])

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk",
            return_value=cached_map,
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk") as mock_save,
    ):
        texts = ["A", "B", "A"]
        embeddings = service.generate_embeddings_batch(texts)

        mock_model.encode.assert_called_once()
        assert mock_model.encode.call_args[0][0] == ["Represent this sentence: B"]

        mock_save.assert_called_once()
        saved_records = mock_save.call_args[0][0]
        assert len(saved_records) == 1

        assert len(embeddings) == 3
        assert embeddings[0] == [9.9] * 384
        assert embeddings[1] == [2.0] * 384
        assert embeddings[2] == [9.9] * 384


async def test_indexing_path_streams_batches_without_accumulating_full_matrix():
    """Verify that backend router indexing streams embeddings in batches to vector store without keeping full matrix in memory."""
    from backend.routers.repositories import index_repository, IndexRequest

    # Generate 6 mock files
    mock_files = [{"path": f"file_{i}.py", "content": f"content_{i}"} for i in range(6)]

    staged_calls = []

    def fake_stage_batch(repo_name, version, chunk_batch, emb_batch, start_chunk_id=0):
        # Record that a batch was staged with limited batch size
        assert len(chunk_batch) <= 2
        assert len(emb_batch) <= 2
        staged_calls.append((chunk_batch, emb_batch))
        return len(chunk_batch)

    mock_model = MagicMock()
    mock_model.encode.side_effect = [
        np.array([[0.1] * 384, [0.2] * 384]),
        np.array([[0.3] * 384, [0.4] * 384]),
        np.array([[0.5] * 384, [0.6] * 384]),
    ]

    with (
        patch(
            "backend.routers.repositories.github_service.clone_repository",
            return_value="/tmp/mock_repo",
        ),
        patch(
            "backend.routers.repositories.github_service.extract_source_files",
            return_value=mock_files,
        ),
        patch(
            "backend.routers.repositories.chunker.chunk_file",
            side_effect=lambda p, c: [{"path": p, "content": c}],
        ),
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk",
            return_value={},
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
        patch(
            "backend.routers.repositories.embedding_service.max_outer_batch_size",
            2,
        ),
        patch(
            "backend.routers.repositories.chroma_store.stage_repository_batch",
            side_effect=fake_stage_batch,
        ),
        patch(
            "backend.routers.repositories.chroma_store.publish_repository_version"
        ) as mock_publish,
    ):
        request = IndexRequest(repo_url="https://github.com/testowner/testrepo")
        result = await index_repository(request)

        assert result["status"] == "indexed"
        assert result["chunks"] == 6

        # Assert staging happened incrementally in 3 separate batches of 2 items
        assert len(staged_calls) == 3
        assert mock_publish.call_count == 1


def test_concurrent_embedding_calls_thread_safety():
    """Verify that multiple threads concurrently calling generate_embeddings_batch are serialized safely by _inference_lock."""
    import concurrent.futures

    service = EmbeddingService(model_name="test-model", max_outer_batch_size=4)

    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, **kwargs: np.array(
        [[0.5] * 384 for _ in texts]
    )

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
    ):

        def worker(thread_id: int):
            texts = [f"Text from thread {thread_id} item {i}" for i in range(5)]
            res = service.generate_embeddings_batch(texts)
            assert len(res) == 5
            for vec in res:
                assert len(vec) == 384
            return len(res)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(16)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 16
        assert all(r == 5 for r in results)


# ---------------------------------------------------------------------------
# Tests for cold-path bulk optimization
# ---------------------------------------------------------------------------


def test_bulk_hash_consistency():
    """Verify compute_chunk_hashes_bulk produces identical results to individual compute_chunk_hash."""
    from services.embedding_service import compute_chunk_hash, compute_chunk_hashes_bulk

    texts = [
        "def foo(): return 1",
        "class Bar:\n    pass",
        "import os\nprint(os.getcwd())",
        "  whitespace  ",
        "",
    ]

    individual = [compute_chunk_hash(t, "BAAI/bge-small-en-v1.5", "1.5") for t in texts]
    bulk = compute_chunk_hashes_bulk(texts, "BAAI/bge-small-en-v1.5", "1.5")

    assert individual == bulk


def test_bulk_l1_lookup():
    """Verify _get_l1_cached_bulk retrieves all cached items in single lock acquisition."""
    from services.embedding_service import (
        _clear_l1_cache,
        _put_l1_cached_bulk,
        _get_l1_cached_bulk,
    )

    _clear_l1_cache()

    # Populate L1 with known data
    data = {
        "hash_a": [1.0] * 384,
        "hash_b": [2.0] * 384,
        "hash_c": [3.0] * 384,
    }
    _put_l1_cached_bulk(data)

    # Bulk lookup: mix of hits and misses
    result = _get_l1_cached_bulk(["hash_a", "hash_missing", "hash_c", "hash_b"])

    assert "hash_a" in result
    assert "hash_b" in result
    assert "hash_c" in result
    assert "hash_missing" not in result
    assert result["hash_a"] == [1.0] * 384
    assert result["hash_c"] == [3.0] * 384


def test_bulk_l2_lookup_and_write():
    """Verify bulk L2 cache write and read roundtrip."""
    from services.embedding_service import (
        _save_embeddings_to_cache_bulk,
        _get_cached_embeddings_bulk,
        _init_sqlite_cache_table,
    )

    _init_sqlite_cache_table()

    # Write bulk records
    records = [
        {
            "chunk_hash": f"test_bulk_hash_{i}",
            "embedding": [float(i)] * 384,
            "model_name": "test-bulk-model",
            "model_version": "1.0",
        }
        for i in range(10)
    ]
    _save_embeddings_to_cache_bulk(records)

    # Read them back in bulk
    hashes = [f"test_bulk_hash_{i}" for i in range(10)]
    result = _get_cached_embeddings_bulk(hashes, "test-bulk-model")

    assert len(result) == 10
    for i in range(10):
        assert result[f"test_bulk_hash_{i}"] == [float(i)] * 384

    # Cleanup
    from storage.migrations import get_db_connection

    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM embedding_cache WHERE model_name = ?",
                ["test-bulk-model"],
            )
    finally:
        conn.close()


def test_all_miss_cold_path():
    """Cold path: 0% cache hits, all items go through model inference."""
    from services.embedding_service import _clear_l1_cache

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-cold", max_outer_batch_size=64)

    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.5] * 384] * 4)

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk") as mock_save,
    ):
        texts = ["alpha", "beta", "gamma", "delta"]
        stats = {}
        embeddings = service.generate_embeddings_batch(texts, stats=stats)

        assert len(embeddings) == 4
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 4
        mock_model.encode.assert_called_once()
        mock_save.assert_called_once()
        assert len(mock_save.call_args[0][0]) == 4


def test_all_hit_warm_path():
    """Warm path: 100% cache hits, no model inference needed."""
    from services.embedding_service import _clear_l1_cache, compute_chunk_hash

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-warm", max_outer_batch_size=64)

    # Pre-compute hashes for the texts
    texts = ["alpha", "beta", "gamma"]
    prefixed = [f"Represent this sentence: {t}" for t in texts]
    cache_map = {}
    for pt in prefixed:
        h = compute_chunk_hash(pt, "test-warm", "1.5")
        cache_map[h] = [9.0] * 384

    mock_model = MagicMock()

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk",
            return_value=cache_map,
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk") as mock_save,
    ):
        stats = {}
        embeddings = service.generate_embeddings_batch(texts, stats=stats)

        assert len(embeddings) == 3
        assert stats["cache_hits"] == 3
        assert stats["cache_misses"] == 0
        mock_model.encode.assert_not_called()
        mock_save.assert_not_called()
        assert all(e == [9.0] * 384 for e in embeddings)


def test_mixed_hit_miss_path():
    """Mixed path: some cache hits, some misses."""
    from services.embedding_service import _clear_l1_cache, compute_chunk_hash

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-mixed", max_outer_batch_size=64)

    # Cache only "alpha" and "gamma"
    texts = ["alpha", "beta", "gamma", "delta"]
    prefixed = [f"Represent this sentence: {t}" for t in texts]
    cache_map = {}
    h_alpha = compute_chunk_hash(prefixed[0], "test-mixed", "1.5")
    h_gamma = compute_chunk_hash(prefixed[2], "test-mixed", "1.5")
    cache_map[h_alpha] = [1.0] * 384
    cache_map[h_gamma] = [3.0] * 384

    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[2.0] * 384, [4.0] * 384])

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk",
            return_value=cache_map,
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk") as mock_save,
    ):
        stats = {}
        embeddings = service.generate_embeddings_batch(texts, stats=stats)

        assert len(embeddings) == 4
        assert stats["cache_hits"] == 2
        assert stats["cache_misses"] == 2
        # Cached items
        assert embeddings[0] == [1.0] * 384
        assert embeddings[2] == [3.0] * 384
        # Encoded items
        assert embeddings[1] == [2.0] * 384
        assert embeddings[3] == [4.0] * 384
        # Only misses encoded
        mock_model.encode.assert_called_once()
        encoded_texts = mock_model.encode.call_args[0][0]
        assert len(encoded_texts) == 2
        # Only misses saved
        mock_save.assert_called_once()
        assert len(mock_save.call_args[0][0]) == 2


def test_model_version_cache_isolation():
    """Embeddings cached under one model version are not returned for another."""
    from services.embedding_service import (
        _clear_l1_cache,
        compute_chunk_hash,
    )

    _clear_l1_cache()

    text = "Represent this sentence: def authenticate()"
    h_v15 = compute_chunk_hash(text, "BAAI/bge-small-en-v1.5", "1.5")
    h_v20 = compute_chunk_hash(text, "BAAI/bge-small-en-v1.5", "2.0")
    h_other = compute_chunk_hash(text, "other-model", "1.5")

    # All hashes are different
    assert h_v15 != h_v20
    assert h_v15 != h_other
    assert h_v20 != h_other


def test_vector_dimensions_preserved():
    """All embeddings must be exactly 384 dimensions."""
    from services.embedding_service import _clear_l1_cache

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-dim", max_outer_batch_size=64)

    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1] * 384, [0.2] * 384, [0.3] * 384])

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
    ):
        embeddings = service.generate_embeddings_batch(["a", "b", "c"])
        for emb in embeddings:
            assert len(emb) == 384


def test_l1_l2_interaction_promotion():
    """L2 hits are promoted to L1 for subsequent instant reuse."""
    from services.embedding_service import (
        _clear_l1_cache,
        _get_l1_cached_bulk,
        compute_chunk_hash,
    )

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-promote", max_outer_batch_size=64)

    texts = ["promote_this_text"]
    prefixed = [f"Represent this sentence: {t}" for t in texts]
    h = compute_chunk_hash(prefixed[0], "test-promote", "1.5")
    l2_map = {h: [7.7] * 384}

    mock_model = MagicMock()

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk",
            return_value=l2_map,
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
    ):
        embeddings = service.generate_embeddings_batch(texts)
        assert embeddings[0] == [7.7] * 384

    # Now check L1 has the promoted entry
    l1_result = _get_l1_cached_bulk([h])
    assert h in l1_result
    assert l1_result[h] == [7.7] * 384


def test_granular_telemetry_fields():
    """Verify new telemetry fields are populated."""
    from services.embedding_service import _clear_l1_cache

    _clear_l1_cache()
    service = EmbeddingService(model_name="test-tel", max_outer_batch_size=64)

    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1] * 384])

    with (
        patch("services.embedding_service._get_model", return_value=mock_model),
        patch(
            "services.embedding_service._get_cached_embeddings_bulk", return_value={}
        ),
        patch("services.embedding_service._save_embeddings_to_cache_bulk"),
    ):
        service.generate_embeddings_batch(["test"])
        tel = service.get_telemetry()

        assert "hash_time_ms" in tel
        assert "l1_lookup_time_ms" in tel
        assert "l2_lookup_time_ms" in tel
        assert "l2_write_time_ms" in tel
        assert "total_embed_time_ms" in tel
        assert tel["hash_time_ms"] >= 0
        assert tel["l1_lookup_time_ms"] >= 0
        assert tel["total_embed_time_ms"] > 0
