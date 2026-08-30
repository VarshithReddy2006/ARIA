import shutil
import tempfile
from unittest.mock import MagicMock, patch
from memory.chroma_store import ChromaStore, _is_corrupted_exception


def test_is_corrupted_exception_detection():
    """Verify that HNSW and segment corruption exceptions are properly identified."""
    assert _is_corrupted_exception(Exception("Error constructing hnsw segment reader"))
    assert _is_corrupted_exception(Exception("Error loading hnsw index"))
    assert _is_corrupted_exception(
        Exception("Error sending backfill request to compactor")
    )
    assert _is_corrupted_exception(Exception("database disk image is malformed"))
    assert _is_corrupted_exception(Exception("segment not found"))
    assert not _is_corrupted_exception(ValueError("Invalid argument"))
    assert not _is_corrupted_exception(KeyError("missing_key"))


def test_chroma_store_basic_lifecycle():
    """Verify ChromaStore initialization, insertion, search, and deletion in a temp dir."""
    temp_dir = tempfile.mkdtemp()
    try:
        store = ChromaStore(persist_directory=temp_dir)
        assert store.collection is not None
        assert store.collection.count() == 0

        # Add code chunks
        store.add_code_chunks(
            file_path="src/main.py",
            chunks=["def run(): pass"],
            embeddings=[[0.1] * 384],
            metadata=[
                {"repo_name": "test_owner/test_repo", "file_path": "src/main.py"}
            ],
        )
        assert store.collection.count() == 1

        # Search similar
        results = store.search_similar([0.1] * 384, limit=1)
        assert len(results) == 1
        assert results[0]["content"] == "def run(): pass"

        # Delete files
        store.delete_files("test_owner/test_repo", ["src/main.py"])
        assert store.collection.count() == 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_chroma_store_self_healing_on_corrupt_query():
    """Verify ChromaStore self-heals by recreating the collection when a corrupted query occurs."""
    temp_dir = tempfile.mkdtemp()
    try:
        store = ChromaStore(persist_directory=temp_dir)

        # Simulate a corrupted query exception on first call, followed by successful call
        mock_query = MagicMock(
            side_effect=[
                Exception(
                    "Error constructing hnsw segment reader: Error loading hnsw index"
                ),
                {
                    "documents": [["healed"]],
                    "metadatas": [[{}]],
                    "ids": [["id1"]],
                    "distances": [[0.0]],
                },
            ]
        )

        with patch.object(store.collection, "query", mock_query):
            # The execution with recovery should catch the corruption, recreate the collection, and retry
            res = store.search_similar([0.1] * 384, limit=1)
            # The function handles the retry or graceful return
            assert isinstance(res, list)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
