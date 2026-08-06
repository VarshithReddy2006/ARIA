"""MCP Server Test Suite (R-020).

Tests the MCP server layer independently of the mcp SDK by verifying
that tools, resources, and prompts correctly delegate to existing services.

All service dependencies are mocked to ensure tests are fast and hermetic.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict


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
def mock_analysis_store():
    mock_analysis = MagicMock()
    mock_analysis.model_dump.return_value = {
        "metadata": {"local_path": "/path"},
        "files": [],
    }
    mock_arch = MagicMock()
    mock_arch.model_dump.return_value = {"summary": "Test arch", "relationships": []}
    return {
        "owner/repo": {
            "analysis": mock_analysis,
            "architecture": mock_arch,
        }
    }


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
    """Verify repository tools delegate to correct services."""

    def test_list_repositories(self, mock_server, mock_analysis_store):
        from mcp.tools.repository_tools import register

        register(mock_server)

        with patch("mcp.dependencies.ANALYSIS_STORE", mock_analysis_store):
            result = mock_server.tools["list_repositories"]()
            repos = json.loads(result)
            assert "owner/repo" in repos

    def test_get_repository_summary_found(self, mock_server, mock_analysis_store):
        from mcp.tools.repository_tools import register

        register(mock_server)

        with patch("mcp.dependencies.ANALYSIS_STORE", mock_analysis_store):
            result = mock_server.tools["get_repository_summary"]("owner", "repo")
            data = json.loads(result)
            assert "analysis" in data
            assert "architecture" in data

    def test_get_repository_summary_not_found(self, mock_server):
        """A missing repository is an MCP tool error, i.e. a raised exception.

        FastMCP converts it to a CallToolResult with isError=True. Returning
        {"error": ...} would instead be a *successful* result, which no
        compliant client can tell apart from real data.
        """
        from mcp.tools.repository_tools import register
        from mcp.errors import ToolFailure

        register(mock_server)

        with patch("mcp.dependencies.ANALYSIS_STORE", {}):
            with pytest.raises(ToolFailure, match="is not indexed"):
                mock_server.tools["get_repository_summary"]("owner", "missing")


class TestSymbolToolExecution:
    """Verify symbol tools delegate to SymbolService."""

    def test_get_file_symbols(self, mock_server):
        from mcp.tools.symbol_tools import register

        register(mock_server)

        from services.symbol_service import SymbolService

        mock_sym = MagicMock()
        mock_sym.model_dump.return_value = {"name": "my_func", "kind": "function"}
        mock_service = MagicMock(spec=SymbolService)
        mock_service.get_file_symbols.return_value = [mock_sym]

        with patch("mcp.dependencies.get_symbol_service", return_value=mock_service):
            result = mock_server.tools["get_file_symbols"]("owner", "repo", "main.py")
            data = json.loads(result)
            assert isinstance(data, list)
            assert data[0]["name"] == "my_func"
            mock_service.get_file_symbols.assert_called_once_with(
                "owner/repo", "main.py"
            )

    def test_get_symbol_definition(self, mock_server):
        from mcp.tools.symbol_tools import register

        register(mock_server)

        from services.symbol_service import SymbolService

        mock_def = MagicMock()
        mock_def.model_dump.return_value = {"name": "my_func", "line": 42}
        mock_service = MagicMock(spec=SymbolService)
        mock_service.get_definition.return_value = mock_def

        with patch("mcp.dependencies.get_symbol_service", return_value=mock_service):
            result = mock_server.tools["get_symbol_definition"](
                "owner", "repo", "my_func"
            )
            data = json.loads(result)
            assert data["name"] == "my_func"
            assert data["line"] == 42

    def test_get_symbol_references(self, mock_server):
        from mcp.tools.symbol_tools import register

        register(mock_server)

        from services.symbol_service import SymbolService

        mock_ref = MagicMock()
        mock_ref.model_dump.return_value = {"file": "other.py", "line": 10}
        mock_service = MagicMock(spec=SymbolService)
        mock_service.get_references.return_value = [mock_ref]

        with patch("mcp.dependencies.get_symbol_service", return_value=mock_service):
            result = mock_server.tools["get_symbol_references"](
                "owner", "repo", "my_func"
            )
            data = json.loads(result)
            assert len(data) == 1
            assert data[0]["file"] == "other.py"


class TestArchitectureToolExecution:
    """Verify architecture tools delegate correctly."""

    def test_get_call_graph(self, mock_server):
        from mcp.tools.architecture_tools import register
        from services.call_graph_service import CallGraphService

        register(mock_server)

        mock_summary = MagicMock()
        mock_summary.model_dump.return_value = {"nodes": [], "edges": []}
        # spec= binds the double to the real class, so a call to a method that
        # does not exist raises AttributeError instead of silently passing.
        mock_service = MagicMock(spec=CallGraphService)
        mock_service.load_summary.return_value = mock_summary

        with patch(
            "mcp.dependencies.get_call_graph_service", return_value=mock_service
        ):
            result = mock_server.tools["get_call_graph"]("owner", "repo")
            data = json.loads(result)
            assert "nodes" in data
            mock_service.load_summary.assert_called_once_with("owner/repo")

    def test_get_call_graph_not_indexed(self, mock_server):
        from mcp.tools.architecture_tools import register
        from services.call_graph_service import CallGraphService

        register(mock_server)

        from mcp.errors import ToolFailure

        mock_service = MagicMock(spec=CallGraphService)
        mock_service.load_summary.return_value = None

        with patch(
            "mcp.dependencies.get_call_graph_service", return_value=mock_service
        ):
            with pytest.raises(ToolFailure, match="No call graph indexed"):
                mock_server.tools["get_call_graph"]("owner", "repo")


class TestSearchToolExecution:
    """Verify search tools delegate correctly."""

    def test_query_codebase(self, mock_server):
        from mcp.tools.search_tools import register

        register(mock_server)

        from services.retrieval_service import RetrievalService

        mock_source = MagicMock()
        mock_source.model_dump.return_value = {"file": "a.py", "score": 0.9}
        mock_service = MagicMock(spec=RetrievalService)
        mock_service.retrieve_and_answer.return_value = {
            "answer": "Test answer",
            "sources": [mock_source],
            "confidence": 0.85,
            "verified": True,
        }

        with patch("mcp.dependencies.get_retrieval_service", return_value=mock_service):
            result = mock_server.tools["query_codebase"](
                "owner", "repo", "what does this do?"
            )
            data = json.loads(result)
            assert data["answer"] == "Test answer"
            assert data["confidence"] == 0.85
            mock_service.retrieve_and_answer.assert_called_once_with(
                "owner/repo", "what does this do?"
            )


class TestAnalysisToolExecution:
    """Verify analysis tools delegate correctly."""

    def test_get_dead_code(self, mock_server):
        from mcp.tools.analysis_tools import register

        register(mock_server)

        from services.dead_code_service import DeadCodeService

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {"dead_functions": ["unused_func"]}
        mock_service = MagicMock(spec=DeadCodeService)
        mock_service.analyze.return_value = mock_result

        with patch("mcp.dependencies.get_dead_code_service", return_value=mock_service):
            result = mock_server.tools["get_dead_code"]("owner", "repo")
            data = json.loads(result)
            assert "dead_functions" in data


class TestReportToolExecution:
    """Verify report tools delegate correctly."""

    def test_generate_report(self, mock_server):
        from mcp.tools.report_tools import register

        register(mock_server)

        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "scores": {"overall": 85, "grade": "B+"},
            "metadata": {"generated_at": "2026-01-01"},
        }
        from services.report.composer import ReportComposer

        mock_composer = MagicMock(spec=ReportComposer)
        mock_composer.compose_report.return_value = mock_report

        with patch("mcp.dependencies.get_report_composer", return_value=mock_composer):
            result = mock_server.tools["generate_report"]("owner", "repo")
            data = json.loads(result)
            assert data["scores"]["overall"] == 85


# ---------------------------------------------------------------------------
# Resource Execution Tests
# ---------------------------------------------------------------------------
class TestResourceExecution:
    """Verify resources expose platform state correctly."""

    def test_list_repositories_resource(self, mock_server, mock_analysis_store):
        from mcp.resources.resource_providers import register

        register(mock_server)

        with patch("mcp.dependencies.ANALYSIS_STORE", mock_analysis_store):
            result = mock_server.resources["repo://repositories"]()
            data = json.loads(result)
            assert "owner/repo" in data

    def test_repository_metadata_resource(self, mock_server, mock_analysis_store):
        from mcp.resources.resource_providers import register

        register(mock_server)

        with patch("mcp.dependencies.ANALYSIS_STORE", mock_analysis_store):
            result = mock_server.resources["repo://{owner}/{repo}/metadata"](
                "owner", "repo"
            )
            data = json.loads(result)
            assert "metadata" in data


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
# DI Integration Tests
# ---------------------------------------------------------------------------
class TestDIIntegration:
    """Verify MCP dependencies bridge reuses existing getters."""

    def test_dependencies_module_exports_analysis_store(self):
        from mcp.dependencies import ANALYSIS_STORE

        assert isinstance(ANALYSIS_STORE, dict)

    def test_dependencies_module_exports_getters(self):
        from mcp import dependencies as deps

        assert callable(deps.get_symbol_service)
        assert callable(deps.get_call_graph_service)
        assert callable(deps.get_dead_code_service)
        assert callable(deps.get_retrieval_service)
        assert callable(deps.get_architecture_service)
        assert callable(deps.get_workspace_service)
        assert callable(deps.get_report_composer)


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
        # Original 7 tools must still be present
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
