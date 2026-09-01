"""Symbol MCP Tools.

Exposes file symbols, symbol definitions, and symbol references.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any

from mcp.errors import require_repo, require_text, tool_boundary
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="get_file_symbols",
        display_name="Get File Symbols",
        description="Extracts AST symbols (classes, functions, methods) for a specific file.",
        category="symbols",
        tags=["symbols", "ast", "file", "classes", "functions"],
        is_read_only=True,
        expected_latency="fast",
    ),
    ToolMetadata(
        name="get_symbol_definition",
        display_name="Get Symbol Definition",
        description="Finds the definition site and location for a given symbol name.",
        category="symbols",
        tags=["symbols", "definition", "lookup"],
        is_read_only=True,
        expected_latency="fast",
    ),
    ToolMetadata(
        name="get_symbol_references",
        display_name="Find Symbol References",
        description="Finds all call sites and references to a given symbol across the codebase.",
        category="symbols",
        tags=["symbols", "references", "callers"],
        is_read_only=True,
        expected_latency="medium",
    ),
]

logger = logging.getLogger("mcp.tools.symbol")


def register(server: Any) -> None:
    """Register symbol tools on the MCP server."""

    @server.tool()
    def get_file_symbols(owner: str, repo: str, file_path: str) -> str:
        """Retrieves symbols defined in a specific file.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            file_path: Path to the file in the repository.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_file_symbols", {"owner": owner, "repo": repo, "file_path": file_path}
        ):
            with tool_boundary("get_file_symbols"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                path = require_text("file_path", file_path)
                client = get_aria_client()
                data = client.get(
                    f"/api/v1/symbols/{owner_clean}/{repo_clean}/file/{path}"
                )
                symbols = data.get("symbols", []) if isinstance(data, dict) else data
                return json.dumps(symbols or [], indent=2, default=str)

    @server.tool()
    def get_symbol_definition(owner: str, repo: str, symbol_name: str) -> str:
        """Retrieves the definition of a specific symbol.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            symbol_name: Name of the symbol to find.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_symbol_definition",
            {"owner": owner, "repo": repo, "symbol_name": symbol_name},
        ):
            with tool_boundary("get_symbol_definition"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                name = require_text("symbol_name", symbol_name)
                client = get_aria_client()
                data = client.get(
                    f"/api/v1/symbols/{owner_clean}/{repo_clean}/definition/{name}"
                )
                definition = (
                    data.get("definition", data) if isinstance(data, dict) else data
                )
                return json.dumps(definition, indent=2, default=str)

    @server.tool()
    def get_symbol_references(owner: str, repo: str, symbol_name: str) -> str:
        """Retrieves references to a specific symbol.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            symbol_name: Name of the symbol to find references for.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "get_symbol_references",
            {"owner": owner, "repo": repo, "symbol_name": symbol_name},
        ):
            with tool_boundary("get_symbol_references"):
                repo_name = require_repo(owner, repo)
                owner_clean, repo_clean = repo_name.split("/", 1)
                name = require_text("symbol_name", symbol_name)
                client = get_aria_client()
                data = client.get(
                    f"/api/v1/symbols/{owner_clean}/{repo_clean}/references/{name}"
                )
                refs = data.get("references", []) if isinstance(data, dict) else data
                return json.dumps(refs or [], indent=2, default=str)
