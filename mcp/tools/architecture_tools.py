"""Architecture MCP Tools.

Exposes call graph, dependency graph, and architecture summary.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any

from mcp.errors import require_repo, tool_boundary
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="get_call_graph",
        display_name="Get Call Graph Summary",
        description="Retrieves the call graph summary showing function call relationships for a repository.",
        category="architecture",
        tags=["architecture", "call-graph", "functions"],
        is_read_only=True,
        expected_latency="medium",
    ),
    ToolMetadata(
        name="get_dependency_graph",
        display_name="Get Module Dependency Graph",
        description="Retrieves the serialized module dependency graph for a repository.",
        category="architecture",
        tags=["architecture", "dependencies", "modules"],
        is_read_only=True,
        expected_latency="medium",
    ),
    ToolMetadata(
        name="get_architecture_summary",
        display_name="Get Architecture Summary",
        description="Retrieves high-level architectural patterns and component relationships for a repository.",
        category="architecture",
        tags=["architecture", "summary", "components"],
        is_read_only=True,
        expected_latency="fast",
    ),
]

logger = logging.getLogger("mcp.tools.architecture")


def register(server: Any) -> None:
    """Register architecture tools on the MCP server."""

    @server.tool()
    def get_call_graph(owner: str, repo: str) -> str:
        """Retrieves the call graph summary for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context("get_call_graph", {"owner": owner, "repo": repo}):
            with tool_boundary("get_call_graph"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.get(f"/api/v1/call-graph/{owner_clean}/{repo_clean}")
                return json.dumps(data, indent=2, default=str)

    @server.tool()
    def get_dependency_graph(owner: str, repo: str) -> str:
        """Retrieves the serialized dependency graph for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_dependency_graph", {"owner": owner, "repo": repo}
        ):
            with tool_boundary("get_dependency_graph"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.get(f"/api/v1/graph/{owner_clean}/{repo_clean}/full")
                return json.dumps(data, indent=2, default=str)

    @server.tool()
    def get_architecture_summary(owner: str, repo: str) -> str:
        """Retrieves the architecture summary for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_architecture_summary", {"owner": owner, "repo": repo}
        ):
            with tool_boundary("get_architecture_summary"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.get(f"/api/v1/architecture/{owner_clean}/{repo_clean}")
                return json.dumps(data, indent=2, default=str)
