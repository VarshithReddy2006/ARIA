"""Architecture MCP Tools.

Exposes call graph, dependency graph, and architecture summary.
"""

import json
import logging
from typing import Any

from mcp.errors import ToolFailure, require_repo, tool_boundary
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
        from mcp.dependencies import get_call_graph_service

        with mcp_request_context("get_call_graph", {"owner": owner, "repo": repo}):
            with tool_boundary("get_call_graph"):
                repo_name = require_repo(owner, repo)
                service = get_call_graph_service()
                # CallGraphService persists its summary behind load_summary();
                # this matches the validated legacy stdio server exactly.
                summary = service.load_summary(repo_name)
                if summary is None:
                    # Wording matches the legacy server verbatim.
                    raise ToolFailure(f"No call graph indexed for '{repo_name}'.")
                result = (
                    summary.model_dump() if hasattr(summary, "model_dump") else summary
                )
                return json.dumps(result, indent=2, default=str)

    @server.tool()
    def get_dependency_graph(owner: str, repo: str) -> str:
        """Retrieves the serialized dependency graph for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_graph_serializer

        with mcp_request_context(
            "get_dependency_graph", {"owner": owner, "repo": repo}
        ):
            with tool_boundary("get_dependency_graph"):
                repo_name = require_repo(owner, repo)
                serializer = get_graph_serializer()
                # GraphSerializer exposes the whole-graph view as get_full_graph();
                # serialize() no longer exists.
                graph_dict = serializer.get_full_graph(repo_name)
                return json.dumps(graph_dict, indent=2, default=str)

    @server.tool()
    def get_architecture_summary(owner: str, repo: str) -> str:
        """Retrieves the architecture summary for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_architecture_service, ANALYSIS_STORE

        with mcp_request_context(
            "get_architecture_summary", {"owner": owner, "repo": repo}
        ):
            with tool_boundary("get_architecture_summary"):
                repo_name = require_repo(owner, repo)
                service = get_architecture_service()
                try:
                    summary = service.get_summary(repo_name)
                except Exception:
                    # Fallback to ANALYSIS_STORE
                    summary = None
                if summary is None:
                    entry = ANALYSIS_STORE.get(repo_name) or {}
                    summary = entry.get("architecture")
                if summary is None:
                    raise ToolFailure(
                        f"No architecture summary indexed for '{repo_name}'."
                    )

                result = (
                    summary.model_dump() if hasattr(summary, "model_dump") else summary
                )
                return json.dumps(result, indent=2, default=str)
