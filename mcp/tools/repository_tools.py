"""Repository MCP Tools.

Exposes repository listing, summary, and analysis capabilities.
All business logic delegates to existing services.
"""

import json
import logging
from typing import Any, Dict, List

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
            persist_analysis_store_sync,
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
                files = github_service.extract_source_files(local_path)
                tech_stack, dependencies = detect_tech_stack_and_deps(files)
                all_file_paths = [f.get("path", "") for f in files if f.get("path")]

                # Generate architecture summary
                import asyncio
                architecture = asyncio.run(
                    generate_architecture_summary(
                        repo_name=repo_name,
                        tech_stack=tech_stack,
                        file_paths=all_file_paths,
                    )
                )

                structure: Dict[str, List[str]] = {}
                for path in all_file_paths:
                    parts = path.split("/")
                    parent = ".".join(parts[:-1]) if len(parts) > 1 else "."
                    name_part = parts[-1]
                    structure.setdefault(parent, []).append(name_part)

                parts = repo_name.split("/")
                owner = parts[0] if len(parts) > 1 else ""
                name = parts[1] if len(parts) > 1 else repo_name

                from models.schemas import RepositoryAnalysis
                analysis = RepositoryAnalysis(
                    structure=structure,
                    dependencies=dependencies,
                    tech_stack=tech_stack,
                    metadata={
                        "owner": owner,
                        "name": name,
                        "local_path": local_path,
                    },
                )

                # Store results
                ANALYSIS_STORE[repo_name] = {
                    "analysis": analysis,
                    "architecture": architecture,
                }

                # Persist synchronously with thread-safe read-merge-write
                try:
                    persist_analysis_store_sync()
                except Exception as exc:
                    logger.warning(
                        "MCP analysis store persistence warning for %s: %s",
                        repo_name,
                        exc,
                    )

                return json.dumps(
                    {
                        "status": "success",
                        "repository": repo_name,
                        "message": f"Repository '{repo_name}' analyzed successfully.",
                    },
                    indent=2,
                )
