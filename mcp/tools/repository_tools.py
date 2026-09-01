"""Repository MCP Tools.

Exposes repository listing, summary, and analysis capabilities.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any

from mcp.errors import require_repo, require_text, tool_boundary
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="list_repositories",
        display_name="List Indexed Repositories",
        description="Lists all repositories currently analyzed and indexed in the system.",
        category="repository",
        tags=["repository", "list", "index"],
        is_read_only=True,
        expected_latency="fast",
    ),
    ToolMetadata(
        name="get_repository_summary",
        display_name="Get Repository Summary",
        description="Retrieves the parsed tech stack, dependency declarations, and high-level structure of an analyzed repository.",
        category="repository",
        tags=["repository", "summary", "tech-stack"],
        is_read_only=True,
        expected_latency="fast",
    ),
    ToolMetadata(
        name="analyze_repository",
        display_name="Analyze Repository",
        description="Initiates deep analysis of a GitHub repository (cloning, symbol extraction, dependency graph building).",
        category="repository",
        tags=["repository", "analysis", "clone", "index"],
        is_read_only=False,
        expected_latency="slow",
        supports_streaming=True,
    ),
]

logger = logging.getLogger("mcp.tools.repository")


def register(server: Any) -> None:
    """Register repository tools on the MCP server."""

    @server.tool()
    def list_repositories() -> str:
        """Lists all repositories currently analyzed and indexed in the system.

        Returns a JSON array of repository identifiers (owner/repo format).
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context("list_repositories"):
            with tool_boundary("list_repositories"):
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

    @server.tool()
    def get_repository_summary(owner: str, repo: str) -> str:
        """Retrieves the parsed tech stack, dependency declarations, and high-level
        structure of an analyzed repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_repository_summary", {"owner": owner, "repo": repo}
        ):
            with tool_boundary("get_repository_summary"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.get(f"/api/v1/analysis/{owner_clean}/{repo_clean}")
                return json.dumps(data, indent=2, default=str)

    @server.tool()
    def analyze_repository(repo_url: str, branch: str = "main") -> str:
        """Initiates analysis of a GitHub repository via ARIA backend.

        Args:
            repo_url: Full GitHub repository URL (e.g., https://github.com/owner/repo).
            branch: Git branch or ref to analyze (default: main).
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "analyze_repository", {"repo_url": repo_url, "branch": branch}
        ):
            with tool_boundary("analyze_repository"):
                require_text("repo_url", repo_url)
                client = get_aria_client()
                resp = client.post(
                    "/api/v1/repositories/analyze",
                    json={
                        "url": repo_url,
                        "branch": branch,
                        "force_rebuild": False,
                    },
                )
                return json.dumps(resp, indent=2, default=str)
