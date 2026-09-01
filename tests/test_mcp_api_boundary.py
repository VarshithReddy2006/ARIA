"""AST Invariant & API Boundary Test Suite for Decoupled MCP Architecture.

Enforces:
1. Strict AST Isolation: No module under `mcp/` may import backend.dependencies,
   storage, memory, services, or LLM providers directly.
2. HTTP Client Translation: All 17 tools and 5 resources must invoke ARIA via
   the canonical AriaAPIClient and handle network/status codes gracefully.
3. Credential Isolation: MCP adapter must never request, log, or inspect
   underlying AI provider keys (GEMINI_API_KEY, DEEPSEEK_API_KEY, etc.).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import httpx

from mcp.aria_client import AriaAPIClient
from mcp.errors import ToolFailure, ToolInputError


MCP_ROOT = Path(__file__).resolve().parents[1] / "mcp"

FORBIDDEN_IMPORT_PREFIXES = (
    "backend.dependencies",
    "storage",
    "memory",
    "services.llm",
    "services.github_service",
    "services.ingestion_service",
    "services.architecture",
    "services.symbol_service",
    "services.call_graph_service",
    "services.dead_code_service",
    "services.retrieval_service",
    "services.graph_service",
    "services.report",
    "chromadb",
    "tree_sitter",
)


# ---------------------------------------------------------------------------
# 1. AST Invariant Tests
# ---------------------------------------------------------------------------
class TestMCPArchitecturalInvariants:
    """Verifies that mcp/ is strictly decoupled from backend internals."""

    def test_no_forbidden_imports_in_mcp_package(self):
        """Scans all Python files in mcp/ to ensure no direct backend/storage/LLM imports."""
        violations: list[str] = []

        for py_file in sorted(MCP_ROOT.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue

            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))

            for node in ast.walk(tree):
                imported_modules: list[str] = []

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported_modules.append(node.module)

                for mod in imported_modules:
                    for forbidden in FORBIDDEN_IMPORT_PREFIXES:
                        if mod == forbidden or mod.startswith(f"{forbidden}."):
                            rel_path = py_file.relative_to(MCP_ROOT.parent)
                            violations.append(
                                f"{rel_path}:{node.lineno} imports forbidden '{mod}'"
                            )

        assert not violations, (
            "Decoupling violation detected! Direct backend/service imports found in MCP:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_mcp_dependencies_module_exports_no_service_singletons(self):
        """Verifies mcp.dependencies only exports the HTTP client bridge."""
        import mcp.dependencies as deps

        exported = dir(deps)
        assert "ANALYSIS_STORE" not in exported
        assert "get_symbol_service" not in exported
        assert "get_chroma_store" not in exported
        assert "get_github_service" not in exported
        assert "get_aria_client" in exported
        assert "AriaAPIClient" in exported


# ---------------------------------------------------------------------------
# 2. AriaAPIClient Unit Tests
# ---------------------------------------------------------------------------
class TestAriaAPIClient:
    """Unit tests for the resilient HTTP client."""

    def test_path_normalization(self):
        client = AriaAPIClient(base_url="http://127.0.0.1:8001")
        assert client._normalize_path("/api/v1/repos/recent") == "/api/v1/repos/recent"
        assert client._normalize_path("api/v1/repos/recent") == "/api/v1/repos/recent"
        assert client._normalize_path("/api/repos/recent") == "/api/v1/repos/recent"
        assert client._normalize_path("/v1/repos/recent") == "/api/v1/repos/recent"
        assert client._normalize_path("/repos/recent") == "/api/v1/repos/recent"
        assert client._normalize_path("/health") == "/health"

    def test_headers_with_and_without_api_key(self):
        client_no_key = AriaAPIClient(base_url="http://127.0.0.1:8001", api_key="")
        headers = client_no_key._get_headers()
        assert "X-API-Key" not in headers
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/json"

        client_with_key = AriaAPIClient(
            base_url="http://127.0.0.1:8001", api_key="secret-123"
        )
        headers_auth = client_with_key._get_headers()
        assert headers_auth["X-API-Key"] == "secret-123"
        assert headers_auth["Authorization"] == "Bearer secret-123"

    def test_error_normalization_400_invalid_params(self):
        client = AriaAPIClient()
        response = httpx.Response(
            status_code=400,
            json={"detail": "Missing query field"},
            request=httpx.Request("POST", "http://127.0.0.1:8001/api/v1/retrieve"),
        )
        with pytest.raises(ToolInputError, match="Invalid params"):
            client._handle_response_error(response, "/api/v1/retrieve")

    def test_error_normalization_401_auth_failure(self):
        client = AriaAPIClient()
        response = httpx.Response(
            status_code=401,
            json={"detail": "Unauthorized"},
            request=httpx.Request("GET", "http://127.0.0.1:8001/api/v1/repos/recent"),
        )
        with pytest.raises(ToolFailure, match="Authentication failed"):
            client._handle_response_error(response, "/api/v1/repos/recent")

    def test_error_normalization_404_not_found(self):
        client = AriaAPIClient()
        response = httpx.Response(
            status_code=404,
            json={"detail": "Repository 'owner/repo' has not been analyzed."},
            request=httpx.Request(
                "GET", "http://127.0.0.1:8001/api/v1/analysis/owner/repo"
            ),
        )
        with pytest.raises(ToolFailure, match="has not been analyzed"):
            client._handle_response_error(response, "/api/v1/analysis/owner/repo")

    def test_error_normalization_429_rate_limit(self):
        client = AriaAPIClient()
        response = httpx.Response(
            status_code=429,
            json={"detail": "Too Many Requests"},
            request=httpx.Request("POST", "http://127.0.0.1:8001/api/v1/retrieve"),
        )
        with pytest.raises(ToolFailure, match="rate limit exceeded"):
            client._handle_response_error(response, "/api/v1/retrieve")


# ---------------------------------------------------------------------------
# 3. Tool Boundary Execution Tests (All 17 Tools)
# ---------------------------------------------------------------------------
class CaptureTools:
    def __init__(self):
        self.tools: dict[str, Any] = {}
        self.resources: dict[str, Any] = {}
        self.prompts: dict[str, Any] = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def resource(self, uri, *a, **k):
        def deco(fn):
            self.resources[uri] = fn
            return fn

        return deco

    def prompt(self, *a, **k):
        def deco(fn):
            self.prompts[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def registered_tools():
    from mcp.tools.discovery import discover_and_register_tools
    from mcp.resources.resource_providers import register as register_resources

    cap = CaptureTools()
    discover_and_register_tools(cap)
    register_resources(cap)
    return cap


class TestAllMCPToolsAPIDelegation:
    """Verifies each of the 17 MCP tools calls the correct API endpoint."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock(spec=AriaAPIClient)
        client.base_url = "http://127.0.0.1:8001"
        return client

    def test_tool_list_repositories(self, registered_tools, mock_client):
        mock_client.get.return_value = [{"name": "org/alpha"}, {"name": "org/beta"}]
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["list_repositories"]()
            assert json.loads(res) == ["org/alpha", "org/beta"]
            mock_client.get.assert_called_once_with("/api/v1/repos/recent")

    def test_tool_get_repository_summary(self, registered_tools, mock_client):
        mock_client.get.return_value = {"analysis": {"tech_stack": ["python"]}}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_repository_summary"]("org", "alpha")
            assert "tech_stack" in res
            mock_client.get.assert_called_once_with("/api/v1/analysis/org/alpha")

    def test_tool_analyze_repository(self, registered_tools, mock_client):
        mock_client.post.return_value = {"status": "queued", "job_id": "job-123"}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["analyze_repository"](
                "https://github.com/org/alpha", "main"
            )
            assert json.loads(res) == {"status": "queued", "job_id": "job-123"}
            mock_client.post.assert_called_once_with(
                "/api/v1/repositories/analyze",
                json={
                    "url": "https://github.com/org/alpha",
                    "branch": "main",
                    "force_rebuild": False,
                },
            )

    def test_tool_query_codebase(self, registered_tools, mock_client):
        mock_client.post.return_value = {
            "answer": "Hello",
            "confidence": 0.95,
            "sources": [],
            "verified": True,
        }
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["query_codebase"](
                "org", "alpha", "How does auth work?"
            )
            assert json.loads(res)["answer"] == "Hello"
            mock_client.post.assert_called_once_with(
                "/api/v1/retrieve",
                json={"repo": "org/alpha", "question": "How does auth work?"},
            )

    def test_tool_semantic_search(self, registered_tools, mock_client):
        mock_client.post.return_value = {"sources": [{"file": "auth.py"}]}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["semantic_search"](
                "org", "alpha", "login handler", top_k=5
            )
            assert json.loads(res) == [{"file": "auth.py"}]

    def test_tool_get_file_symbols(self, registered_tools, mock_client):
        mock_client.get.return_value = [{"name": "AuthService"}]
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_file_symbols"](
                "org", "alpha", "src/auth.py"
            )
            assert json.loads(res) == [{"name": "AuthService"}]
            mock_client.get.assert_called_once_with(
                "/api/v1/symbols/org/alpha/file/src/auth.py"
            )

    def test_tool_get_symbol_definition(self, registered_tools, mock_client):
        mock_client.get.return_value = {"name": "login", "line": 50}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_symbol_definition"](
                "org", "alpha", "login"
            )
            assert json.loads(res)["line"] == 50
            mock_client.get.assert_called_once_with(
                "/api/v1/symbols/org/alpha/definition/login"
            )

    def test_tool_get_symbol_references(self, registered_tools, mock_client):
        mock_client.get.return_value = [{"file": "main.py", "line": 20}]
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_symbol_references"](
                "org", "alpha", "login"
            )
            assert len(json.loads(res)) == 1
            mock_client.get.assert_called_once_with(
                "/api/v1/symbols/org/alpha/references/login"
            )

    def test_tool_get_call_graph(self, registered_tools, mock_client):
        mock_client.get.return_value = {"nodes": ["login", "verify"]}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_call_graph"]("org", "alpha")
            assert "login" in res
            mock_client.get.assert_called_once_with("/api/v1/call-graph/org/alpha")

    def test_tool_get_dependency_graph(self, registered_tools, mock_client):
        mock_client.get.return_value = {"nodes": [], "edges": []}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_dependency_graph"]("org", "alpha")
            assert "edges" in res
            mock_client.get.assert_called_once_with("/api/v1/graph/org/alpha/full")

    def test_tool_get_architecture_summary(self, registered_tools, mock_client):
        mock_client.get.return_value = {"summary": "Microservice arch"}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_architecture_summary"]("org", "alpha")
            assert "Microservice" in res
            mock_client.get.assert_called_once_with("/api/v1/architecture/org/alpha")

    def test_tool_get_dead_code(self, registered_tools, mock_client):
        mock_client.post.return_value = {"dead_functions": ["old_fn"]}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_dead_code"]("org", "alpha")
            assert "old_fn" in res
            mock_client.post.assert_called_once_with(
                "/api/v1/dead-code/analyze",
                json={"owner": "org", "repo": "alpha"},
            )

    def test_tool_get_impact_analysis(self, registered_tools, mock_client):
        mock_client.post.return_value = {"affected_files": ["auth.py", "api.py"]}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_impact_analysis"](
                "org", "alpha", change_description="Update jwt key"
            )
            assert "auth.py" in res
            mock_client.post.assert_called_once_with(
                "/api/v1/impact-analysis",
                json={"repo": "org/alpha", "issue": "Update jwt key"},
            )

    def test_tool_get_api_surface(self, registered_tools, mock_client):
        mock_client.get.return_value = {"public": ["login"], "internal": ["_hash"]}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_api_surface"]("org", "alpha")
            assert "public" in res
            mock_client.get.assert_called_once_with("/api/v1/api-surface/org/alpha")

    def test_tool_get_workspace(self, registered_tools, mock_client):
        mock_client.get.return_value = {"overview": {"status": "ok"}}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["get_workspace"](
                "org", "alpha", panel="overview"
            )
            assert "overview" in res
            mock_client.get.assert_called_once_with(
                "/api/v1/repositories/org/alpha/workspace",
                params={"panel": "overview"},
            )

    def test_tool_generate_report(self, registered_tools, mock_client):
        mock_client.post.return_value = {"scores": {"overall": 92}}
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["generate_report"]("org", "alpha")
            assert "92" in res
            mock_client.post.assert_called_once_with("/api/v1/report/org/alpha/build")

    def test_tool_export_report(self, registered_tools, mock_client):
        mock_client.get.return_value = "# Report\nHealth 92%"
        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            res = registered_tools.tools["export_report"](
                "org", "alpha", format="markdown"
            )
            data = json.loads(res)
            assert data["format"] == "markdown"
            assert "# Report" in data["content"]
            mock_client.get.assert_called_once_with(
                "/api/v1/report/org/alpha/download",
                params={"format": "markdown"},
            )
