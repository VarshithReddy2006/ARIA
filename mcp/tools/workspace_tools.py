"""Workspace MCP Tools.

Exposes workspace context generation.
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
    def get_workspace(owner: str, repo: str, panel: str = "overview", file: Optional[str] = None, symbol: Optional[str] = None) -> str:
        """Retrieves a contextual workspace view for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            panel: Which panel of the workspace to view (e.g., overview, file, symbol).
            file: Optional file path if viewing file panel.
            symbol: Optional symbol name if viewing symbol panel.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_workspace_service
        from models.workspace import WorkspaceState

        with mcp_request_context("get_workspace", {"owner": owner, "repo": repo, "panel": panel, "file": file, "symbol": symbol}):
            with tool_boundary("get_workspace"):
                repo_name = require_repo(owner, repo)
                service = get_workspace_service()
                # WorkspaceState's fields are repository/active_panel/selected_file/
                # selected_symbol. The previous call passed panel/current_file/
                # current_symbol, which pydantic silently discarded, and omitted the
                # required repository field, so this tool could never succeed.
                state = WorkspaceState(
                    repository=repo_name,
                    active_panel=panel,
                    selected_file=file,
                    selected_symbol=symbol,
                )
                workspace = service.get_workspace(repo_name, state=state)
                serialized = workspace.model_dump() if hasattr(workspace, "model_dump") else workspace
                return json.dumps(serialized, indent=2, default=str)
