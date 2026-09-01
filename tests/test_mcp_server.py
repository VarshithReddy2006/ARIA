"""MCP Server Test Suite (R-020).

Tests the MCP server layer independently of the mcp SDK by verifying
that tools, resources, and prompts correctly delegate to the ARIA HTTP client.

All service dependencies are mocked to ensure tests are fast and hermetic.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict

from mcp.aria_client import AriaAPIClient
from mcp.errors import ToolFailure


# ---------------------------------------------------------------------------
# Helper: Capture tool functions registered via @server.tool()
# ---------------------------------------------------------------------------
class MockMCPServer:
    """Mock FastMCP server that captures registered tools, resources, and prompts."""

    def __init__(self):
        self.tools: Dict[str, Any] = {}
        self.resources: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, uri: str, *args, **kwargs):
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator

    def prompt(self, *args, **kwargs):
        def decorator(fn):
            self.prompts[fn.__name__] = fn
            return fn

        return decorator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_server():
    return MockMCPServer()


@pytest.fixture
def mock_client():
    client = MagicMock(spec=AriaAPIClient)
    client.base_url = "http://127.0.0.1:8001"
    return client


# ---------------------------------------------------------------------------
# Tool Registration Tests
# ---------------------------------------------------------------------------
class TestToolRegistration:
    """Verify all tool modules register the expected tools."""

    def test_repository_tools_register(self, mock_server):
        from mcp.tools.repository_tools import register

        register(mock_server)
        assert "list_repositories" in mock_server.tools
        assert "get_repository_summary" in mock_server.tools
        assert "analyze_repository" in mock_server.tools

    def test_architecture_tools_register(self, mock_server):
        from mcp.tools.architecture_tools import register

        register(mock_server)
        assert "get_call_graph" in mock_server.tools
        assert "get_dependency_graph" in mock_server.tools
        assert "get_architecture_summary" in mock_server.tools

    def test_symbol_tools_register(self, mock_server):
        from mcp.tools.symbol_tools import register

        register(mock_server)
        assert "get_file_symbols" in mock_server.tools
        assert "get_symbol_definition" in mock_server.tools
        assert "get_symbol_references" in mock_server.tools

    def test_search_tools_register(self, mock_server):
        from mcp.tools.search_tools import register

        register(mock_server)
        assert "query_codebase" in mock_server.tools
        assert "semantic_search" in mock_server.tools

    def test_analysis_tools_register(self, mock_server):
        from mcp.tools.analysis_tools import register

        register(mock_server)
        assert "get_dead_code" in mock_server.tools
        assert "get_impact_analysis" in mock_server.tools
        assert "get_api_surface" in mock_server.tools

    def test_workspace_tools_register(self, mock_server):
        from mcp.tools.workspace_tools import register

        register(mock_server)
        assert "get_workspace" in mock_server.tools

    def test_report_tools_register(self, mock_server):
        from mcp.tools.report_tools import register

        register(mock_server)
        assert "generate_report" in mock_server.tools
        assert "export_report" in mock_server.tools


# ---------------------------------------------------------------------------
# Resource Registration Tests
# ---------------------------------------------------------------------------
class TestResourceRegistration:
    """Verify all resources are registered."""

    def test_resources_register(self, mock_server):
        from mcp.resources.resource_providers import register

        register(mock_server)
        assert "repo://repositories" in mock_server.resources
        assert "repo://{owner}/{repo}/metadata" in mock_server.resources
        assert "repo://{owner}/{repo}/architecture" in mock_server.resources
        assert "repo://{owner}/{repo}/call-graph" in mock_server.resources
        assert "repo://{owner}/{repo}/symbols" in mock_server.resources


# ---------------------------------------------------------------------------
# Prompt Registration Tests
# ---------------------------------------------------------------------------
class TestPromptRegistration:
    """Verify all prompts are registered."""

    def test_prompts_register(self, mock_server):
        from mcp.prompts.prompt_templates import register

        register(mock_server)
        assert "explain_repository" in mock_server.prompts
        assert "review_architecture" in mock_server.prompts
        assert "trace_execution_path" in mock_server.prompts
        assert "analyze_blast_radius" in mock_server.prompts
        assert "generate_health_report" in mock_server.prompts


# ---------------------------------------------------------------------------
# Tool Execution Tests
# ---------------------------------------------------------------------------
class TestRepositoryToolExecution:
    """Verify repository tools delegate to correct API endpoints."""

    def test_list_repositories(self, mock_server, mock_client):
        from mcp.tools.repository_tools import register

        register(mock_server)
        mock_client.get.return_value = [{"name": "owner/repo"}]

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["list_repositories"]()
            repos = json.loads(result)
            assert "owner/repo" in repos
            mock_client.get.assert_called_once_with("/api/v1/repos/recent")

    def test_get_repository_summary_found(self, mock_server, mock_client):
        from mcp.tools.repository_tools import register

        register(mock_server)
        mock_client.get.return_value = {
            "analysis": {"tech_stack": ["python"]},
            "architecture": {"summary": "test"},
        }

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["get_repository_summary"]("owner", "repo")
            data = json.loads(result)
            assert "analysis" in data
            assert "architecture" in data
            mock_client.get.assert_called_once_with("/api/v1/analysis/owner/repo")

    def test_get_repository_summary_not_found(self, mock_server, mock_client):
        from mcp.tools.repository_tools import register

        register(mock_server)
        mock_client.get.side_effect = ToolFailure(
            "Repository 'owner/missing' is not indexed."
        )

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            with pytest.raises(ToolFailure, match="is not indexed"):
                mock_server.tools["get_repository_summary"]("owner", "missing")


class TestSymbolToolExecution:
    """Verify symbol tools delegate to ARIA symbols API."""

    def test_get_file_symbols(self, mock_server, mock_client):
        from mcp.tools.symbol_tools import register

        register(mock_server)
        mock_client.get.return_value = [{"name": "my_func", "kind": "function"}]

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["get_file_symbols"]("owner", "repo", "main.py")
            data = json.loads(result)
            assert isinstance(data, list)
            assert data[0]["name"] == "my_func"
            mock_client.get.assert_called_once_with(
                "/api/v1/symbols/owner/repo/file/main.py"
            )

    def test_get_symbol_definition(self, mock_server, mock_client):
        from mcp.tools.symbol_tools import register

        register(mock_server)
        mock_client.get.return_value = {"name": "my_func", "line": 42}

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["get_symbol_definition"](
                "owner", "repo", "my_func"
            )
            data = json.loads(result)
            assert data["name"] == "my_func"
            assert data["line"] == 42
            mock_client.get.assert_called_once_with(
                "/api/v1/symbols/owner/repo/definition/my_func"
            )

    def test_get_symbol_references(self, mock_server, mock_client):
        from mcp.tools.symbol_tools import register

        register(mock_server)
        mock_client.get.return_value = [{"file": "other.py", "line": 10}]

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["get_symbol_references"](
                "owner", "repo", "my_func"
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["file"] == "other.py"
            mock_client.get.assert_called_once_with(
                "/api/v1/symbols/owner/repo/references/my_func"
            )


class TestArchitectureToolExecution:
    """Verify architecture tools delegate correctly to ARIA REST endpoints."""

    def test_get_call_graph(self, mock_server, mock_client):
        from mcp.tools.architecture_tools import register

        register(mock_server)
        mock_client.get.return_value = {"nodes": [], "edges": []}

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["get_call_graph"]("owner", "repo")
            data = json.loads(result)
            assert "nodes" in data
            mock_client.get.assert_called_once_with("/api/v1/call-graph/owner/repo")

    def test_get_call_graph_not_indexed(self, mock_server, mock_client):
        from mcp.tools.architecture_tools import register

        register(mock_server)
        mock_client.get.side_effect = ToolFailure(
            "No call graph indexed for 'owner/repo'."
        )

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            with pytest.raises(ToolFailure, match="No call graph indexed"):
                mock_server.tools["get_call_graph"]("owner", "repo")


class TestSearchToolExecution:
    """Verify search tools delegate correctly to ARIA retrieval API."""

    def test_query_codebase(self, mock_server, mock_client):
        from mcp.tools.search_tools import register

        register(mock_server)
        mock_client.post.return_value = {
            "answer": "Test answer",
            "sources": [{"file": "a.py", "score": 0.9}],
            "confidence": 0.85,
            "verified": True,
        }

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["query_codebase"](
                "owner", "repo", "what does this do?"
            )
            data = json.loads(result)
            assert data["answer"] == "Test answer"
            assert data["confidence"] == 0.85
            mock_client.post.assert_called_once_with(
                "/api/v1/retrieve",
                json={"repo": "owner/repo", "question": "what does this do?"},
            )


class TestAnalysisToolExecution:
    """Verify analysis tools delegate correctly."""

    def test_get_dead_code(self, mock_server, mock_client):
        from mcp.tools.analysis_tools import register

        register(mock_server)
        mock_client.post.return_value = {"dead_functions": ["unused_func"]}

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["get_dead_code"]("owner", "repo")
            data = json.loads(result)
            assert "dead_functions" in data
            mock_client.post.assert_called_once_with(
                "/api/v1/dead-code/analyze",
                json={"owner": "owner", "repo": "repo"},
            )


class TestReportToolExecution:
    """Verify report tools delegate correctly."""

    def test_generate_report(self, mock_server, mock_client):
        from mcp.tools.report_tools import register

        register(mock_server)
        mock_client.post.return_value = {
            "scores": {"overall": 85, "grade": "B+"},
            "metadata": {"generated_at": "2026-01-01"},
        }

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.tools["generate_report"]("owner", "repo")
            data = json.loads(result)
            assert data["scores"]["overall"] == 85
            mock_client.post.assert_called_once_with("/api/v1/report/owner/repo/build")


# ---------------------------------------------------------------------------
# Resource Execution Tests
# ---------------------------------------------------------------------------
class TestResourceExecution:
    """Verify resources expose platform state correctly via API client."""

    def test_list_repositories_resource(self, mock_server, mock_client):
        from mcp.resources.resource_providers import register

        register(mock_server)
        mock_client.get.return_value = [{"name": "owner/repo"}]

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.resources["repo://repositories"]()
            data = json.loads(result)
            assert "owner/repo" in data

    def test_repository_metadata_resource(self, mock_server, mock_client):
        from mcp.resources.resource_providers import register

        register(mock_server)
        mock_client.get.return_value = {"analysis": {"tech_stack": ["python"]}}

        with patch("mcp.dependencies.get_aria_client", return_value=mock_client):
            result = mock_server.resources["repo://{owner}/{repo}/metadata"](
                "owner", "repo"
            )
            data = json.loads(result)
            assert "tech_stack" in data


# ---------------------------------------------------------------------------
# Prompt Execution Tests
# ---------------------------------------------------------------------------
class TestPromptExecution:
    """Verify prompts produce correct instruction strings."""

    def test_explain_repository_prompt(self, mock_server):
        from mcp.prompts.prompt_templates import register

        register(mock_server)

        result = mock_server.prompts["explain_repository"]("owner", "repo")
        assert "owner/repo" in result
        assert "get_repository_summary" in result
        assert "get_architecture_summary" in result

    def test_review_architecture_prompt(self, mock_server):
        from mcp.prompts.prompt_templates import register

        register(mock_server)

        result = mock_server.prompts["review_architecture"]("owner", "repo")
        assert "owner/repo" in result
        assert "get_dead_code" in result

    def test_trace_execution_path_prompt(self, mock_server):
        from mcp.prompts.prompt_templates import register

        register(mock_server)

        result = mock_server.prompts["trace_execution_path"](
            "owner", "repo", "my_function"
        )
        assert "my_function" in result
        assert "get_symbol_definition" in result

    def test_analyze_blast_radius_prompt(self, mock_server):
        from mcp.prompts.prompt_templates import register

        register(mock_server)

        result = mock_server.prompts["analyze_blast_radius"](
            "owner", "repo", "src/main.py"
        )
        assert "src/main.py" in result
        assert "get_impact_analysis" in result

    def test_generate_health_report_prompt(self, mock_server):
        from mcp.prompts.prompt_templates import register

        register(mock_server)

        result = mock_server.prompts["generate_health_report"]("owner", "repo")
        assert "owner/repo" in result
        assert "generate_report" in result


# ---------------------------------------------------------------------------
# Observability Integration Tests
# ---------------------------------------------------------------------------
class TestObservabilityIntegration:
    """Verify MCP observability bridge works correctly."""

    def test_mcp_request_context_sets_request_id(self):
        from mcp.observability import mcp_request_context
        from core.observability.context import request_id_var

        with mcp_request_context("test_tool") as req_id:
            assert req_id  # Should be a non-empty UUID string
            assert request_id_var.get() == req_id

        # Context should be cleaned up
        assert request_id_var.get() == ""

    def test_mcp_request_context_records_metrics(self):
        from mcp.observability import mcp_request_context
        from core.observability.metrics import metrics_collector

        # Record the initial state
        initial_requests = dict(metrics_collector.http_requests_total)

        with mcp_request_context("test_metrics_tool"):
            pass

        # Check that a metric was recorded
        key = ("MCP", "tools/test_metrics_tool", 200)
        assert metrics_collector.http_requests_total.get(key, 0) > initial_requests.get(
            key, 0
        )

    def test_mcp_request_context_records_error_metrics(self):
        from mcp.observability import mcp_request_context
        from core.observability.metrics import metrics_collector

        initial_requests = dict(metrics_collector.http_requests_total)

        with pytest.raises(ValueError):
            with mcp_request_context("test_error_tool"):
                raise ValueError("test error")

        key = ("MCP", "tools/test_error_tool", 500)
        assert metrics_collector.http_requests_total.get(key, 0) > initial_requests.get(
            key, 0
        )


# ---------------------------------------------------------------------------
# Client DI Integration Tests
# ---------------------------------------------------------------------------
class TestClientDIIntegration:
    """Verify MCP dependencies module exports AriaAPIClient."""

    def test_dependencies_module_exports_client(self):
        from mcp.dependencies import AriaAPIClient, get_aria_client

        assert callable(get_aria_client)
        client = get_aria_client()
        assert isinstance(client, AriaAPIClient)


# ---------------------------------------------------------------------------
# Server Creation Tests
# ---------------------------------------------------------------------------
class TestServerCreation:
    """Verify server creation and configuration."""

    def test_create_server_without_sdk_raises(self):
        """If the mcp SDK is not installed, create_server should raise."""
        with patch("mcp.server.FastMCP", None):
            from mcp.server import create_server

            with pytest.raises(RuntimeError, match="mcp.*SDK.*not installed"):
                create_server()


# ---------------------------------------------------------------------------
# Legacy Backward Compatibility Tests
# ---------------------------------------------------------------------------
class TestLegacyBackwardCompatibility:
    """Ensure the legacy mcp_server.py still works."""

    def test_legacy_tools_list_unchanged(self):
        from backend.mcp_server import TOOLS

        tool_names = [t["name"] for t in TOOLS]
        assert "list_repositories" in tool_names
        assert "get_repository_summary" in tool_names
        assert "get_file_symbols" in tool_names
        assert "get_symbol_definition" in tool_names
        assert "get_symbol_references" in tool_names
        assert "get_call_graph" in tool_names
        assert "get_dead_code" in tool_names
        assert "query_codebase" in tool_names

    def test_legacy_execute_tool_list(self):
        from backend.mcp_server import execute_tool

        store = {"owner/repo": {"analysis": MagicMock(), "architecture": MagicMock()}}
        result = execute_tool("list_repositories", {}, store, None, None, None, None)
        assert "owner/repo" in result
