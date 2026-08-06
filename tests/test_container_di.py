"""Unit tests for FastAPI Dependency Injection and RIA Container Integration (Task 5 / R-017)."""

from unittest.mock import MagicMock
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from ria.container import Container
from backend.dependencies import (
    get_container,
    get_git_client,
    get_parser_service,
    get_repository_manager,
    get_ingestion_service,
    get_commit_resolver,
    get_symbol_service,
)
from services.symbol_service import SymbolService


class TestContainerDI:
    """Test suite verifying Container integration and FastAPI dependency injection."""

    def test_get_container_fallback_outside_request(self) -> None:
        """Verify get_container resolves a valid global Container when outside a Request."""
        container = get_container()
        assert isinstance(container, Container)
        assert container.settings is not None
        assert container.git is not None

    def test_get_container_from_request_state(self) -> None:
        """Verify get_container extracts the Container from request.app.state."""
        mock_container = MagicMock(spec=Container)
        app = FastAPI()
        app.state.container = mock_container

        @app.get("/test-container")
        def route(container: Container = Depends(get_container)):
            return {"container_id": id(container)}

        client = TestClient(app)
        res = client.get("/test-container")
        assert res.status_code == 200
        assert res.json()["container_id"] == id(mock_container)

    def test_container_domain_port_getters(self) -> None:
        """Verify container port getters resolve expected services."""
        container = get_container()
        assert get_git_client() == container.git
        assert get_parser_service() == container.parser_service
        assert get_repository_manager() == container.repository_manager
        assert get_ingestion_service() == container.ingestion_service
        assert get_commit_resolver() == container.commit_resolver

    def test_fastapi_dependency_overrides(self) -> None:
        """Verify FastAPI app.dependency_overrides allows clean mocking of services."""
        app = FastAPI()
        mock_symbols = MagicMock(spec=SymbolService)
        mock_symbols.get_file_symbols.return_value = []

        @app.get("/test-symbols/{owner}/{repo}")
        def test_route(
            owner: str,
            repo: str,
            service: SymbolService = Depends(get_symbol_service),
        ):
            symbols = service.get_file_symbols(f"{owner}/{repo}", "main.py")
            return {"count": len(symbols)}

        app.dependency_overrides[get_symbol_service] = lambda: mock_symbols

        client = TestClient(app)
        res = client.get("/test-symbols/testowner/testrepo")
        assert res.status_code == 200
        assert res.json()["count"] == 0
        mock_symbols.get_file_symbols.assert_called_once_with(
            "testowner/testrepo", "main.py"
        )

    def test_api_lifespan_container_initialization_and_shutdown(self) -> None:
        """Verify backend.api app lifespan initializes app.state.container and shuts down cleanly."""
        from backend.api import app

        with TestClient(app) as client:
            assert hasattr(app.state, "container")
            assert isinstance(app.state.container, Container)
            assert app.state.git is not None
            assert app.state.parser_service is not None

            # Perform a health check query
            res = client.get("/health")
            assert res.status_code == 200
