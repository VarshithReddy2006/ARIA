"""Repository MCP Tools.

Exposes repository listing, summary, and analysis capabilities.
All business logic delegates to existing services.
"""

import json
import logging
from typing import Any

from mcp.errors import ToolFailure, require_repo, require_text, tool_boundary
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
        from mcp.dependencies import ANALYSIS_STORE

        with mcp_request_context("list_repositories"):
            repos = list(ANALYSIS_STORE.keys())
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
        from mcp.dependencies import ANALYSIS_STORE

        with mcp_request_context(
            "get_repository_summary", {"owner": owner, "repo": repo}
        ):
            with tool_boundary("get_repository_summary"):
                repo_name = require_repo(owner, repo)
                if repo_name not in ANALYSIS_STORE:
                    raise ToolFailure(
                        f"Repository '{repo_name}' is not indexed. Analyze it first."
                    )

                entry = ANALYSIS_STORE[repo_name]
                result = {
                    "analysis": (
                        entry["analysis"].model_dump()
                        if hasattr(entry["analysis"], "model_dump")
                        else entry["analysis"]
                    ),
                    "architecture": (
                        entry["architecture"].model_dump()
                        if hasattr(entry["architecture"], "model_dump")
                        else entry["architecture"]
                    ),
                }
                return json.dumps(result, indent=2, default=str)

    @server.tool()
    def analyze_repository(repo_url: str, branch: str = "main") -> str:
        """Initiates analysis of a GitHub repository. Clones the repository,
        extracts symbols, builds dependency graphs, and generates architecture summaries.

        This is a long-running operation that may take several minutes for large repositories.

        Args:
            repo_url: Full GitHub repository URL (e.g., https://github.com/owner/repo).
            branch: Git branch or ref to analyze (default: main).
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import (
            ANALYSIS_STORE,
            get_github_service,
            _persist_analysis_store,
        )
        from services.ingestion_service import (
            detect_tech_stack_and_deps,
            parse_repo_name,
        )
        from services.architecture_summary_service import generate_architecture_summary

        with mcp_request_context(
            "analyze_repository", {"repo_url": repo_url, "branch": branch}
        ):
            with tool_boundary("analyze_repository"):
                require_text("repo_url", repo_url)
                github_service = get_github_service()
                repo_name = parse_repo_name(repo_url)

                # Clone. GitHubService exposes clone_repository(); clone_repo()
                # no longer exists.
                local_path = github_service.clone_repository(repo_url, branch=branch)

                # Parse tech stack
                analysis = detect_tech_stack_and_deps(local_path, repo_name)

                # Generate architecture summary
                architecture = generate_architecture_summary(analysis, local_path)

                # Store results
                ANALYSIS_STORE[repo_name] = {
                    "analysis": analysis,
                    "architecture": architecture,
                }

                # Persist asynchronously (best-effort in sync context)
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(_persist_analysis_store())
                    else:
                        loop.run_until_complete(_persist_analysis_store())
                except RuntimeError:
                    pass  # No event loop available in stdio context

                return json.dumps(
                    {
                        "status": "success",
                        "repository": repo_name,
                        "message": f"Repository '{repo_name}' analyzed successfully.",
                    },
                    indent=2,
                )
