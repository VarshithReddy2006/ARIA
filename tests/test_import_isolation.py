"""Test module import isolation and ensure zero network I/O during startup.

Ensures that importing backend.api executes purely locally without triggering
any remote network operations (such as QdrantClient.get_collections).
"""

import sys
import time
from unittest.mock import MagicMock, patch
import pytest


def test_import_backend_api_zero_network():
    """Verify importing backend.api performs zero network I/O and finishes quickly."""
    orig_modules = dict(sys.modules)
    try:
        # Unload backend and router modules to test a fresh import cycle
        modules_to_unload = [
            mod for mod in list(sys.modules.keys())
            if mod.startswith("backend") or mod.startswith("memory") or mod.startswith("services")
        ]
        for mod in modules_to_unload:
            sys.modules.pop(mod, None)

        # Mock qdrant_client if not installed or patch it if installed
        mock_client_instance = MagicMock()
        mock_client_instance.get_collections.side_effect = RuntimeError(
            "Network call attempted during import: get_collections()"
        )

        mock_qdrant_client_cls = MagicMock(return_value=mock_client_instance)
        mock_qdrant_module = MagicMock()
        mock_qdrant_module.QdrantClient = mock_qdrant_client_cls

        with patch.dict(sys.modules, {"qdrant_client": mock_qdrant_module, "qdrant_client.models": MagicMock()}):
            start_time = time.perf_counter()
            import backend.api  # noqa: F401
            elapsed = time.perf_counter() - start_time

            # Ensure get_collections was never invoked during import
            assert not mock_client_instance.get_collections.called, (
                "QdrantClient.get_collections was called during backend.api import!"
            )

            # Ensure import completes quickly (< 500 ms)
            assert elapsed < 0.5, f"Import took too long: {elapsed:.3f}s (expected < 0.5s)"
            assert backend.api.app is not None
    finally:
        sys.modules.clear()
        sys.modules.update(orig_modules)


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
        assert mock_client_instance.get_collections.call_count == call_count_after_first_op
