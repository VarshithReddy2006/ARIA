"""MCP Resource Providers.

Exposes repository metadata, architecture, and analysis data as
MCP resources. All data comes from existing stores — no new
storage mechanisms are created.
"""

import json
import logging
from typing import Any

from mcp.errors import ToolFailure, require_repo, tool_boundary
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
        from mcp.dependencies import ANALYSIS_STORE
        return json.dumps(list(ANALYSIS_STORE.keys()), indent=2)

    @server.resource(TEMPLATE_METADATA)
    def repository_metadata(owner: str, repo: str) -> str:
        """Repository analysis metadata including tech stack, dependencies, and file structure."""
        from mcp.dependencies import ANALYSIS_STORE
        with tool_boundary("repository_metadata"):
            repo_name = require_repo(owner, repo)
            if repo_name not in ANALYSIS_STORE:
                raise ToolFailure(f"Repository '{repo_name}' is not indexed.")
            entry = ANALYSIS_STORE[repo_name]["analysis"]
            data = entry.model_dump() if hasattr(entry, "model_dump") else entry
            return json.dumps(data, indent=2, default=str)

    @server.resource(TEMPLATE_ARCHITECTURE)
    def repository_architecture(owner: str, repo: str) -> str:
        """Repository architecture summary including component relationships and reading order."""
        from mcp.dependencies import ANALYSIS_STORE
        with tool_boundary("repository_architecture"):
            repo_name = require_repo(owner, repo)
            if repo_name not in ANALYSIS_STORE:
                raise ToolFailure(f"Repository '{repo_name}' is not indexed.")
            entry = ANALYSIS_STORE[repo_name]["architecture"]
            data = entry.model_dump() if hasattr(entry, "model_dump") else entry
            return json.dumps(data, indent=2, default=str)

    @server.resource(TEMPLATE_CALL_GRAPH)
    def repository_call_graph(owner: str, repo: str) -> str:
        """Repository call graph showing function call relationships."""
        from mcp.dependencies import get_call_graph_service
        with tool_boundary("repository_call_graph"):
            repo_name = require_repo(owner, repo)
            service = get_call_graph_service()
            # load_summary() is the current public API; get_graph_summary() is gone.
            result = service.load_summary(repo_name)
            if result is None:
                raise ToolFailure(f"No call graph indexed for '{repo_name}'.")
            return json.dumps(result.model_dump(), indent=2, default=str)

    @server.resource(TEMPLATE_SYMBOLS)
    def repository_symbols(owner: str, repo: str) -> str:
        """All symbols (classes, functions, methods) indexed for the repository."""
        from mcp.dependencies import get_symbol_service
        with tool_boundary("repository_symbols"):
            repo_name = require_repo(owner, repo)
            service = get_symbol_service()
            # SymbolService.load() returns the persisted SymbolIndex (or None);
            # get_all_symbols() no longer exists. The index carries .symbols.
            index = service.load(repo_name)
            if index is None:
                raise ToolFailure(f"No symbols indexed for '{repo_name}'.")
            result = getattr(index, "symbols", []) or []
            data = [s.model_dump() if hasattr(s, "model_dump") else s for s in result]
            return json.dumps(data, indent=2, default=str)
