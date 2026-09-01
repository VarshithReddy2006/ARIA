"""MCP Resource Providers.

Exposes repository metadata, architecture, and analysis data as MCP resources.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any

from mcp.errors import require_repo, tool_boundary
from mcp.resources.namespace import (
    TEMPLATE_REPOSITORIES,
    TEMPLATE_METADATA,
    TEMPLATE_ARCHITECTURE,
    TEMPLATE_CALL_GRAPH,
    TEMPLATE_SYMBOLS,
)

logger = logging.getLogger("mcp.resources")


def register(server: Any) -> None:
    """Register all MCP resources on the server using canonical URIs."""

    @server.resource(TEMPLATE_REPOSITORIES)
    def list_repositories_resource() -> str:
        """List of all analyzed repositories."""
        from mcp.dependencies import get_aria_client

        client = get_aria_client()
        data = client.get("/api/v1/repos/recent")
        if isinstance(data, list):
            repos = [
                item.get("name", "")
                for item in data
                if isinstance(item, dict) and item.get("name")
            ]
        elif isinstance(data, dict):
            repos = list(data.keys())
        else:
            repos = []
        return json.dumps(repos, indent=2)

    @server.resource(TEMPLATE_METADATA)
    def repository_metadata(owner: str, repo: str) -> str:
        """Repository analysis metadata including tech stack, dependencies, and file structure."""
        from mcp.dependencies import get_aria_client

        with tool_boundary("repository_metadata"):
            repo_name = require_repo(owner, repo)
            owner_clean, repo_clean = repo_name.split("/", 1)
            client = get_aria_client()
            data = client.get(f"/api/v1/analysis/{owner_clean}/{repo_clean}")
            analysis = data.get("analysis", data) if isinstance(data, dict) else data
            return json.dumps(analysis, indent=2, default=str)

    @server.resource(TEMPLATE_ARCHITECTURE)
    def repository_architecture(owner: str, repo: str) -> str:
        """Repository architecture summary including component relationships and reading order."""
        from mcp.dependencies import get_aria_client

        with tool_boundary("repository_architecture"):
            repo_name = require_repo(owner, repo)
            owner_clean, repo_clean = repo_name.split("/", 1)
            client = get_aria_client()
            data = client.get(f"/api/v1/architecture/{owner_clean}/{repo_clean}")
            return json.dumps(data, indent=2, default=str)

    @server.resource(TEMPLATE_CALL_GRAPH)
    def repository_call_graph(owner: str, repo: str) -> str:
        """Repository call graph showing function call relationships."""
        from mcp.dependencies import get_aria_client

        with tool_boundary("repository_call_graph"):
            repo_name = require_repo(owner, repo)
            owner_clean, repo_clean = repo_name.split("/", 1)
            client = get_aria_client()
            data = client.get(f"/api/v1/call-graph/{owner_clean}/{repo_clean}")
            return json.dumps(data, indent=2, default=str)

    @server.resource(TEMPLATE_SYMBOLS)
    def repository_symbols(owner: str, repo: str) -> str:
        """All symbols (classes, functions, methods) indexed for the repository."""
        from mcp.dependencies import get_aria_client

        with tool_boundary("repository_symbols"):
            repo_name = require_repo(owner, repo)
            owner_clean, repo_clean = repo_name.split("/", 1)
            client = get_aria_client()
            data = client.get(f"/api/v1/symbols/{owner_clean}/{repo_clean}")
            return json.dumps(data, indent=2, default=str)
