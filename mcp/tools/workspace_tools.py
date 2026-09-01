"""Workspace MCP Tools.

Exposes workspace context generation.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any, Optional

from mcp.errors import require_repo, tool_boundary
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="get_workspace",
        display_name="Get Developer Workspace",
        description="Retrieves multi-panel coordinated developer workspace state.",
        category="workspace",
        tags=["workspace", "ui", "state"],
        is_read_only=True,
        expected_latency="fast",
    ),
]

logger = logging.getLogger("mcp.tools.workspace")


def register(server: Any) -> None:
    """Register workspace tools on the MCP server."""

    @server.tool()
    def get_workspace(
        owner: str,
        repo: str,
        panel: str = "overview",
        file: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> str:
        """Retrieves a contextual workspace view for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            panel: Which panel of the workspace to view (e.g., overview, file, symbol).
            file: Optional file path if viewing file panel.
            symbol: Optional symbol name if viewing symbol panel.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_workspace",
            {
                "owner": owner,
                "repo": repo,
                "panel": panel,
                "file": file,
                "symbol": symbol,
            },
        ):
            with tool_boundary("get_workspace"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                params: dict[str, Any] = {"panel": panel}
                if file:
                    params["file"] = file
                if symbol:
                    params["symbol"] = symbol

                client = get_aria_client()
                data = client.get(
                    f"/api/v1/repositories/{owner_clean}/{repo_clean}/workspace",
                    params=params,
                )
                return json.dumps(data, indent=2, default=str)
