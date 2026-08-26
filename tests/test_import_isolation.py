"""Test module import isolation and ensure zero network I/O during startup.

Ensures that importing backend.api executes purely locally without triggering
any remote network operations (such as QdrantClient.get_collections).
"""

from unittest.mock import MagicMock, patch


def test_import_backend_api_zero_network():
    """Verify importing backend.api performs zero network I/O."""
    with patch("memory.qdrant_store.QdrantClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.get_collections.side_effect = RuntimeError(
            "Network call attempted: get_collections()"
        )
        mock_client_cls.return_value = mock_client_instance

        # Verify backend.api is importable and app exists without triggering Qdrant network calls
        import backend.api

        assert backend.api.app is not None
        assert not mock_client_instance.get_collections.called, (
            "QdrantClient.get_collections was called during backend.api import!"
        )


def test_qdrant_store_lazy_ensure_collections():
    """Verify QdrantStore construction does not perform network calls and ensures collections lazily."""
    from memory.qdrant_store import QdrantStore

    with (
        patch("memory.qdrant_store.QdrantClient") as mock_client_cls,
        patch("memory.qdrant_store.VectorParams", MagicMock()),
        patch("memory.qdrant_store.Distance", MagicMock()),
        patch("memory.qdrant_store.models", MagicMock()),
    ):
        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance

        # 1. Construction must NOT trigger get_collections()
        store = QdrantStore(
            url="https://mock-cluster.cloud.qdrant.io:6333",
            api_key="mock-key-secret",
            vector_size=1536,
        )

        assert not mock_client_instance.get_collections.called, (
            "QdrantStore.__init__ called get_collections() eagerly!"
        )
        assert store._collections_ensured is False

        # 2. First operation triggers lazy ensure_collections
        mock_client_instance.get_collections.return_value = MagicMock(collections=[])
        mock_client_instance.scroll.return_value = ([], None)

        store._active_version("test-org/test-repo")

        assert mock_client_instance.get_collections.called, (
            "get_collections was not called on first operation!"
        )
        assert store._collections_ensured is True
        call_count_after_first_op = mock_client_instance.get_collections.call_count

        # 3. Subsequent operations do NOT re-trigger ensure_collections
        store._active_version("test-org/test-repo")
        assert (
            mock_client_instance.get_collections.call_count == call_count_after_first_op
        )
