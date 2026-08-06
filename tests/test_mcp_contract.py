"""Public MCP API Contract Validation Test Suite (R-020A).

Ensures strict API contract stability for the exposed MCP layer:
- Tool identifiers and discovery schemas
- Canonical resource URI namespaces
- Prompt template names and orchestration rules
- Tool metadata schema completeness
- Server capability and version declarations
- Task lifecycle state model validity
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from mcp.metadata import TOOL_METADATA_REGISTRY, list_all_tool_metadata, get_tool_metadata
from mcp.resources.namespace import (
    TEMPLATE_REPOSITORIES,
    TEMPLATE_METADATA,
    TEMPLATE_ARCHITECTURE,
    TEMPLATE_CALL_GRAPH,
    TEMPLATE_SYMBOLS,
    build_repositories_uri,
    build_repo_resource_uri,
    parse_resource_uri,
)
from mcp.version import (
    SERVER_NAME,
    SERVER_VERSION,
    PROTOCOL_VERSION,
    IMPLEMENTATION_NAME,
    get_server_metadata,
)
from mcp.lifecycle import TaskState, TaskTracker, global_task_tracker


class MockServer:
    def __init__(self):
        self.tools = {}
        self.resources = {}
        self.prompts = {}

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


class TestToolDiscoveryContract:
    """Contract tests for dynamic tool discovery."""

    def test_all_17_tools_discovered(self):
        mock_server = MockServer()
        from mcp.tools.discovery import discover_and_register_tools

        modules = discover_and_register_tools(mock_server)

        expected_tools = {
            "list_repositories",
            "get_repository_summary",
            "analyze_repository",
            "get_call_graph",
            "get_dependency_graph",
            "get_architecture_summary",
            "get_file_symbols",
            "get_symbol_definition",
            "get_symbol_references",
            "query_codebase",
            "semantic_search",
            "get_dead_code",
            "get_impact_analysis",
            "get_api_surface",
            "get_workspace",
            "generate_report",
            "export_report",
        }

        assert set(mock_server.tools.keys()) == expected_tools

    def test_discovery_is_deterministic(self):
        mock_server1 = MockServer()
        mock_server2 = MockServer()
        from mcp.tools.discovery import discover_and_register_tools

        mods1 = discover_and_register_tools(mock_server1)
        mods2 = discover_and_register_tools(mock_server2)

        assert mods1 == mods2
        assert mods1 == sorted(mods1)


class TestToolMetadataContract:
    """Contract tests for tool metadata completeness."""

    def test_all_tools_have_registered_metadata(self):
        mock_server = MockServer()
        from mcp.tools.discovery import discover_and_register_tools

        discover_and_register_tools(mock_server)

        for tool_name in mock_server.tools.keys():
            meta = get_tool_metadata(tool_name)
            assert meta is not None, f"Tool '{tool_name}' missing metadata declaration"
            assert meta.name == tool_name
            assert meta.display_name
            assert meta.description
            assert meta.category in {
                "repository",
                "architecture",
                "symbols",
                "search",
                "analysis",
                "workspace",
                "reporting",
            }

    def test_metadata_fields_schema(self):
        meta_list = list_all_tool_metadata()
        assert len(meta_list) >= 17
        for meta in meta_list:
            assert isinstance(meta.is_read_only, bool)
            assert meta.expected_latency in {"fast", "medium", "slow"}
            assert isinstance(meta.supports_streaming, bool)


class TestResourceNamespaceContract:
    """Contract tests for canonical resource URI namespace stability."""

    def test_canonical_uri_templates(self):
        assert TEMPLATE_REPOSITORIES == "repo://repositories"
        assert TEMPLATE_METADATA == "repo://{owner}/{repo}/metadata"
        assert TEMPLATE_ARCHITECTURE == "repo://{owner}/{repo}/architecture"
        assert TEMPLATE_CALL_GRAPH == "repo://{owner}/{repo}/call-graph"
        assert TEMPLATE_SYMBOLS == "repo://{owner}/{repo}/symbols"

    def test_resource_uri_builders(self):
        assert build_repositories_uri() == "repo://repositories"
        assert (
            build_repo_resource_uri("facebook", "react", "metadata")
            == "repo://facebook/react/metadata"
        )

    def test_resource_uri_parser(self):
        parsed_root = parse_resource_uri("repo://repositories")
        assert parsed_root == {"resource_type": "repositories"}

        parsed_meta = parse_resource_uri("repo://owner/repo/metadata")
        assert parsed_meta == {"owner": "owner", "repo": "repo", "resource_type": "metadata"}

        assert parse_resource_uri("invalid://path") is None

    def test_registered_resources_match_canonical_templates(self):
        mock_server = MockServer()
        from mcp.resources.resource_providers import register

        register(mock_server)

        assert "repo://repositories" in mock_server.resources
        assert "repo://{owner}/{repo}/metadata" in mock_server.resources
        assert "repo://{owner}/{repo}/architecture" in mock_server.resources
        assert "repo://{owner}/{repo}/call-graph" in mock_server.resources
        assert "repo://{owner}/{repo}/symbols" in mock_server.resources


class TestPromptOrchestrationContract:
    """Contract tests for prompt tool-only orchestration."""

    def test_prompts_reference_valid_tools_only(self):
        mock_server = MockServer()
        from mcp.tools.discovery import discover_and_register_tools
        from mcp.prompts.prompt_templates import register as register_prompts

        discover_and_register_tools(mock_server)
        register_prompts(mock_server)

        expected_prompts = {
            "explain_repository",
            "review_architecture",
            "trace_execution_path",
            "analyze_blast_radius",
            "generate_health_report",
        }
        assert set(mock_server.prompts.keys()) == expected_prompts

        # Verify explain_repository references tool names
        explain_prompt = mock_server.prompts["explain_repository"]("owner", "repo")
        assert "`get_repository_summary`" in explain_prompt
        assert "`get_architecture_summary`" in explain_prompt
        assert "`get_call_graph`" in explain_prompt


class TestServerVersionContract:
    """Contract tests for server versioning and capabilities."""

    def test_version_metadata(self):
        meta = get_server_metadata()
        assert meta["server_name"] == "Repo Intelligence Agent"
        assert meta["server_version"] == "1.5.0"
        assert meta["protocol_version"] == "2024-11-05"
        assert meta["implementation_name"] == "ria-mcp-server"
        assert "stdio" in meta["supported_transports"]
        assert "tools" in meta["capabilities"]


class TestTaskLifecycleContract:
    """Contract tests for extensible task lifecycle state model."""

    def test_task_states_include_core_and_extended(self):
        assert TaskState.QUEUED == "queued"
        assert TaskState.RUNNING == "running"
        assert TaskState.PROGRESS == "progress"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
        assert TaskState.CANCELLED == "cancelled"
        assert TaskState.TIMED_OUT == "timed_out"
        assert TaskState.RETRYING == "retrying"

    def test_task_tracker_lifecycle_flow(self):
        tracker = TaskTracker()
        t = tracker.start_task("task-1", "Starting")
        assert t.state == TaskState.RUNNING

        p = tracker.update_progress("task-1", 50.0, "Halfway")
        assert p.progress_percentage == 50.0

        c = tracker.complete_task("task-1", "Done")
        assert c.state == TaskState.COMPLETED
        assert c.progress_percentage == 100.0
