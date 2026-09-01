"""Analysis MCP Tools.

Exposes dead code detection, impact analysis, and API surface classification.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any, Optional

from mcp.errors import (
    ToolInputError,
    require_repo,
    require_text,
    tool_boundary,
)
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="get_dead_code",
        display_name="Get Dead Code Analysis",
        description="Identifies orphan modules, dead functions, and unreferenced dependency chains.",
        category="analysis",
        tags=["analysis", "dead-code", "refactoring", "hygiene"],
        is_read_only=True,
        expected_latency="medium",
    ),
    ToolMetadata(
        name="get_impact_analysis",
        display_name="Get Change Impact Analysis",
        description=(
            "Predicts which files and components a proposed change will affect, "
            "given a natural-language description of that change."
        ),
        category="analysis",
        tags=["analysis", "impact", "blast-radius", "change-risk"],
        is_read_only=True,
        expected_latency="medium",
    ),
    ToolMetadata(
        name="get_api_surface",
        display_name="Get API Surface Classification",
        description="Classifies public vs internal API symbols and detects breaking changes.",
        category="analysis",
        tags=["analysis", "api-surface", "breaking-changes"],
        is_read_only=True,
        expected_latency="fast",
    ),
]

logger = logging.getLogger("mcp.tools.analysis")


def register(server: Any) -> None:
    """Register analysis tools on the MCP server."""

    @server.tool()
    def get_dead_code(owner: str, repo: str) -> str:
        """Identifies potentially dead or unused code in the repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context("get_dead_code", {"owner": owner, "repo": repo}):
            with tool_boundary("get_dead_code"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.post(
                    "/api/v1/dead-code/analyze",
                    json={"owner": owner_clean, "repo": repo_clean},
                )
                return json.dumps(data, indent=2, default=str)

    @server.tool()
    def get_impact_analysis(
        owner: str,
        repo: str,
        change_description: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """Predicts which files a proposed change will affect.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            change_description: Natural-language description of the intended
                change, e.g. an issue body or "rename the auth middleware".
            file_path: Deprecated alias for change_description.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_impact_analysis",
            {"owner": owner, "repo": repo, "change_description": change_description},
        ):
            with tool_boundary("get_impact_analysis"):
                repo_name = require_repo(owner, repo)
                effective = (
                    change_description if change_description is not None else file_path
                )
                if effective is None:
                    raise ToolInputError(
                        "Invalid params: Missing required argument(s): "
                        "change_description."
                    )
                if file_path is not None and change_description is None:
                    logger.warning(
                        "get_impact_analysis received deprecated alias 'file_path'; "
                        "use 'change_description' instead."
                    )
                effective_text = require_text("change_description", effective)

                client = get_aria_client()
                data = client.post(
                    "/api/v1/impact-analysis",
                    json={"repo": repo_name, "issue": effective_text},
                )
                return json.dumps(data, indent=2, default=str)

    @server.tool()
    def get_api_surface(owner: str, repo: str) -> str:
        """Classifies the API surface of the repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context("get_api_surface", {"owner": owner, "repo": repo}):
            with tool_boundary("get_api_surface"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                client = get_aria_client()
                data = client.get(f"/api/v1/api-surface/{owner_clean}/{repo_clean}")
                return json.dumps(data, indent=2, default=str)
