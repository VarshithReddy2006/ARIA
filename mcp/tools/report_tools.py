"""Report MCP Tools.

Exposes comprehensive report generation and export capabilities.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any

from mcp.errors import ToolInputError, require_repo, require_text, tool_boundary
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="generate_report",
        display_name="Generate Repository Health Report",
        description="Composes a comprehensive repository health report with overall score and grade.",
        category="reporting",
        tags=["report", "health-score", "composition"],
        is_read_only=True,
        expected_latency="medium",
    ),
    ToolMetadata(
        name="export_report",
        display_name="Export Health Report",
        description="Exports the composed health report in Markdown or HTML format.",
        category="reporting",
        tags=["report", "export", "markdown", "html"],
        is_read_only=True,
        expected_latency="fast",
    ),
]

logger = logging.getLogger("mcp.tools.report")


def register(server: Any) -> None:
    """Register report tools on the MCP server."""

    @server.tool()
    def generate_report(owner: str, repo: str) -> str:
        """Generates a comprehensive analysis report for a repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context("generate_report", {"owner": owner, "repo": repo}):
            with tool_boundary("generate_report"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.post(f"/api/v1/report/{owner_clean}/{repo_clean}/build")
                return json.dumps(data, indent=2, default=str)

    @server.tool()
    def export_report(owner: str, repo: str, format: str = "markdown") -> str:
        """Exports a generated report in the specified format (markdown or html).

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            format: Output format ('markdown' or 'html').
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "export_report", {"owner": owner, "repo": repo, "format": format}
        ):
            with tool_boundary("export_report"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                fmt = require_text("format", format).lower()
                if fmt not in {"markdown", "html"}:
                    raise ToolInputError(
                        "Invalid params: Argument 'format' must be one of: "
                        "html, markdown."
                    )
                client = get_aria_client()
                content = client.get(
                    f"/api/v1/report/{owner_clean}/{repo_clean}/download",
                    params={"format": fmt},
                )
                return json.dumps(
                    {"format": fmt, "content": str(content)},
                    indent=2,
                    default=str,
                )
