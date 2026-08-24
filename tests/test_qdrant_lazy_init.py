"""Regression test for lazy, network-safe Qdrant initialization."""

from unittest.mock import MagicMock, patch
from memory.qdrant_store import QdrantStore


def test_qdrant_constructor_has_zero_network_io():
    """Verify that QdrantStore constructor performs zero remote calls and zero collection creation."""
    mock_client = MagicMock()
    with patch("memory.qdrant_store.QdrantClient", return_value=mock_client):
        store = QdrantStore(url="http://remote-qdrant:6333", api_key="secret")
        # Ensure no network operations were performed in __init__
        assert mock_client.get_collections.call_count == 0
        assert mock_client.create_collection.call_count == 0
        assert mock_client.upsert.call_count == 0
        assert store._collections_ensured is False


def test_first_write_ensures_collections_and_succeeds():
    """Verify that the first write lazily creates collections and performs the upsert."""
    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []

    with (
        patch("memory.qdrant_store.QdrantClient", return_value=mock_client),
        patch("memory.qdrant_store.PointStruct", side_effect=lambda **kwargs: kwargs),
        patch("memory.qdrant_store.VectorParams", return_value=MagicMock()),
        patch("memory.qdrant_store.Distance", MagicMock()),
        patch("memory.qdrant_store.models", MagicMock()),
    ):
        store = QdrantStore(url="http://remote-qdrant:6333")
        assert store._collections_ensured is False

        # First write
        store.add_code_chunks_bulk(
            ids=["chunk_1"],
            documents=["def foo(): pass"],
            embeddings=[[0.1] * 384],
            metadatas=[{"repo_name": "test_repo", "file_path": "foo.py"}],
        )

        # Verified collections ensured and upsert called
        assert store._collections_ensured is True
        assert mock_client.get_collections.call_count >= 1
        assert mock_client.create_collection.call_count == 2
        assert mock_client.upsert.call_count == 1
