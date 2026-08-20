"""Regression tests for backend dependencies and Qdrant configuration."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend.dependencies import (
    _SINGLETONS,
    analysis_registry,
    get_qdrant_store,
    get_vector_store,
)
from memory.vector_store import ProductionVectorStore


def test_analysis_registry_has_no_type_none_builders():
    """Assert that zero analysis capabilities are registered with type(None) as builder class."""
    type_none_entries = [
        name
        for name, node in analysis_registry.nodes.items()
        # Both operators are checked on purpose: ``is`` catches the plain
        # ``type(None)`` sentinel, while ``==`` also catches a registration whose
        # metaclass overrides ``__eq__``. Narrowing to ``is`` alone would weaken
        # the regression guard, so E721 is suppressed for this line only.
        if node.service_class is type(None) or node.service_class == type(None)  # noqa: E721
    ]

    assert len(type_none_entries) == 0, (
        f"Found analysis capabilities registered with type(None): {type_none_entries}"
    )


def test_get_qdrant_store_passes_all_configurations():
    """Verify that get_qdrant_store passes url, grpc_port, prefer_grpc, api_key, and timeout to QdrantStore."""
    with (
        patch("backend.dependencies._SINGLETONS", {}),
        patch("backend.dependencies.settings") as mock_settings,
        patch("backend.dependencies.QdrantStore") as mock_qdrant_cls,
    ):
        mock_settings.qdrant_url = "https://remote-qdrant.example.com:6333"
        mock_settings.qdrant_grpc_port = 6334
        mock_settings.qdrant_prefer_grpc = False
        mock_settings.qdrant_api_key = "test-secret-api-key-123"
        mock_settings.qdrant_timeout = 25.0

        mock_instance = MagicMock()
        mock_qdrant_cls.return_value = mock_instance

        store = get_qdrant_store()

        assert store is mock_instance
        mock_qdrant_cls.assert_called_once_with(
            url="https://remote-qdrant.example.com:6333",
            grpc_port=6334,
            prefer_grpc=False,
            api_key="test-secret-api-key-123",
            timeout=25.0,
        )


def test_get_vector_store_selects_qdrant_as_primary():
    """Verify that get_vector_store selects Qdrant as primary when vector_store_backend is qdrant."""
    mock_qdrant = MagicMock()
    mock_chroma = MagicMock()

    with (
        patch("backend.dependencies._SINGLETONS", {}),
        patch("backend.dependencies.settings") as mock_settings,
        patch(
            "backend.dependencies.get_qdrant_store", return_value=mock_qdrant
        ) as mock_get_qdrant,
        patch(
            "backend.dependencies.get_chroma_store", return_value=mock_chroma
        ) as mock_get_chroma,
    ):
        mock_settings.vector_store_backend = "qdrant"
        mock_settings.vector_store_enable_fallback = False

        vector_store = get_vector_store()

        assert isinstance(vector_store, ProductionVectorStore)
        assert vector_store.primary is mock_qdrant
        assert vector_store.fallback is mock_chroma
        assert vector_store.active_backend == "qdrant"
        assert vector_store.enable_fallback is False
        mock_get_qdrant.assert_called_once()
        mock_get_chroma.assert_called_once()


def test_production_vector_store_no_fallback_when_disabled():
    """Verify that when fallback is disabled, primary failures raise immediately without invoking fallback."""
    mock_qdrant = MagicMock()
    mock_qdrant.search_similar.side_effect = ConnectionError(
        "Qdrant connection refused"
    )

    mock_chroma = MagicMock()

    pvs = ProductionVectorStore(
        primary_store=mock_qdrant,
        fallback_store=mock_chroma,
        enable_fallback=False,
    )

    assert pvs.active_backend == "qdrant"

    with pytest.raises(ConnectionError, match="Qdrant connection refused"):
        pvs.search_similar_code([0.1, 0.2, 0.3], limit=5)

    # Verify fallback was NOT called
    mock_chroma.search_similar.assert_not_called()
    mock_chroma.search_similar_code.assert_not_called()
    assert pvs.telemetry.chroma_fallback_count == 0


def test_health_endpoint_reports_active_vector_backend():
    """Verify that /health reports the active vector store backend (qdrant or chroma)."""
    client = TestClient(app)

    # 1. When vector_store active_backend is qdrant
    mock_pvs_qdrant = MagicMock()
    mock_pvs_qdrant.active_backend = "qdrant"

    with patch.dict(_SINGLETONS, {"vector_store": mock_pvs_qdrant}):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["vector_db"] == "qdrant"

    # 2. When vector_store active_backend is chroma
    mock_pvs_chroma = MagicMock()
    mock_pvs_chroma.active_backend = "chroma"

    with patch.dict(_SINGLETONS, {"vector_store": mock_pvs_chroma}):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["vector_db"] == "chroma"
