"""Unit and regression tests for bounded outer batching in EmbeddingService."""

import logging
from unittest.mock import MagicMock, patch
import numpy as np

from services.embedding_service import EmbeddingService


def test_embedding_multiple_outer_batches_and_persistence(caplog):
    """Verify that multiple outer batches are used and each batch persists incrementally."""
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

        # 1. Assert model.encode was called 3 times
        assert mock_model.encode.call_count == 3

        # 2. Check each batch size passed to encode
        calls = mock_model.encode.call_args_list
        assert len(calls[0][0][0]) == 2
        assert len(calls[1][0][0]) == 2
        assert len(calls[2][0][0]) == 1

        # 3. Assert incremental persistence occurred after each batch
        assert len(saved_batches) == 3
        assert len(saved_batches[0]) == 2
        assert len(saved_batches[1]) == 2
        assert len(saved_batches[2]) == 1

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

    import hashlib

    hash_a = hashlib.md5("Represent this sentence: A".encode("utf-8")).hexdigest()
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
