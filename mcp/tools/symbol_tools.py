"""Symbol MCP Tools.

Exposes file symbols, symbol definitions, and symbol references.
"""

import json
import logging
from typing import Any

from mcp.errors import ToolFailure, require_repo, require_text, tool_boundary
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
        from mcp.dependencies import get_symbol_service

        with mcp_request_context("get_file_symbols", {"owner": owner, "repo": repo, "file_path": file_path}):
            with tool_boundary("get_file_symbols"):
                repo_name = require_repo(owner, repo)
                path = require_text("file_path", file_path)
                service = get_symbol_service()
                symbols = service.get_file_symbols(repo_name, path)
                # get_file_symbols is Optional[List]; legacy treats an absent
                # index as a business failure with this exact wording.
                if symbols is None:
                    raise ToolFailure(
                        f"No symbol index found for file '{path}' in repo '{repo_name}'."
                    )
                result = [sym.model_dump() if hasattr(sym, "model_dump") else sym for sym in symbols]
                return json.dumps(result, indent=2, default=str)

    @server.tool()
    def get_symbol_definition(owner: str, repo: str, symbol_name: str) -> str:
        """Retrieves the definition of a specific symbol.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            symbol_name: Name of the symbol to find.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_symbol_service

        with mcp_request_context("get_symbol_definition", {"owner": owner, "repo": repo, "symbol_name": symbol_name}):
            with tool_boundary("get_symbol_definition"):
                repo_name = require_repo(owner, repo)
                name = require_text("symbol_name", symbol_name)
                service = get_symbol_service()
                symbol = service.get_definition(repo_name, name)
                if not symbol:
                    raise ToolFailure(
                        f"Symbol '{name}' not found in repo '{repo_name}'."
                    )
                result = symbol.model_dump() if hasattr(symbol, "model_dump") else symbol
                return json.dumps(result, indent=2, default=str)

    @server.tool()
    def get_symbol_references(owner: str, repo: str, symbol_name: str) -> str:
        """Retrieves references to a specific symbol.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            symbol_name: Name of the symbol to find references for.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_symbol_service

        with mcp_request_context("get_symbol_references", {"owner": owner, "repo": repo, "symbol_name": symbol_name}):
            with tool_boundary("get_symbol_references"):
                repo_name = require_repo(owner, repo)
                name = require_text("symbol_name", symbol_name)
                service = get_symbol_service()
                # get_references is Optional[List]; "no references" is a valid
                # answer, so normalise to [] rather than raising (parity with
                # the legacy BUG-004 fix).
                refs = service.get_references(repo_name, name)
                result = [
                    ref.model_dump() if hasattr(ref, "model_dump") else ref
                    for ref in (refs or [])
                ]
                return json.dumps(result, indent=2, default=str)
