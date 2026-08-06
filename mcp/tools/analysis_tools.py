"""Analysis MCP Tools.

Exposes dead code detection, impact analysis, and API surface classification.
"""

import json
import logging
from typing import Any, Optional

from mcp.errors import (
    ToolFailure,
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
        from mcp.dependencies import get_dead_code_service

        with mcp_request_context("get_dead_code", {"owner": owner, "repo": repo}):
            with tool_boundary("get_dead_code"):
                repo_name = require_repo(owner, repo)
                service = get_dead_code_service()
                result = service.analyze(repo_name)
                serialized = result.model_dump() if hasattr(result, "model_dump") else result
                return json.dumps(serialized, indent=2, default=str)

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
                A bare file path is accepted but yields a weaker prediction.
            file_path: Deprecated alias for change_description, kept so existing
                clients keep working. Ignored when change_description is given.

        Exactly one of change_description or file_path is required. Both are
        declared optional so that either spelling satisfies the schema; the
        requirement is enforced below.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_impact_analysis_service

        with mcp_request_context(
            "get_impact_analysis",
            {"owner": owner, "repo": repo, "change_description": change_description},
        ):
            with tool_boundary("get_impact_analysis"):
                repo_name = require_repo(owner, repo)

                # Backward compatibility: file_path was this tool's original
                # parameter name. change_description wins when both arrive; the
                # deprecation notice goes to the log only, never to the client.
                if change_description is not None and file_path is not None:
                    logger.warning(
                        "get_impact_analysis received both 'change_description' and "
                        "the deprecated 'file_path'; using 'change_description'."
                    )
                elif file_path is not None:
                    logger.warning(
                        "get_impact_analysis parameter 'file_path' is deprecated; "
                        "use 'change_description'."
                    )
                effective = (
                    change_description if change_description is not None else file_path
                )
                if effective is None:
                    raise ToolInputError(
                        "Invalid params: Missing required argument(s): "
                        "change_description."
                    )
                effective = require_text("change_description", effective)

                service = get_impact_analysis_service()
                # ImpactAnalysisService.analyze_change(repo_name, issue_text) is the
                # current public API and the one the REST layer uses
                # (backend/routers/architecture.py). analyze_impact() never existed,
                # and it took a file path, hence the parameter rename.
                result = service.analyze_change(repo_name, effective)
                serialized = result.model_dump() if hasattr(result, "model_dump") else result
                return json.dumps(serialized, indent=2, default=str)

    @server.tool()
    def get_api_surface(owner: str, repo: str) -> str:
        """Classifies the API surface of the repository.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_api_surface_service

        with mcp_request_context("get_api_surface", {"owner": owner, "repo": repo}):
            with tool_boundary("get_api_surface"):
                repo_name = require_repo(owner, repo)
                service = get_api_surface_service()
                # APISurfaceService persists the classified surface; load() is the
                # read API. classify() no longer exists.
                result = service.load(repo_name)
                if result is None:
                    raise ToolFailure(f"No API surface indexed for '{repo_name}'.")
                serialized = result.model_dump() if hasattr(result, "model_dump") else result
                return json.dumps(serialized, indent=2, default=str)
