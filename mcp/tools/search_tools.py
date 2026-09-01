"""Search MCP Tools.

Exposes codebase querying and semantic search via ARIA retrieval API.
All requests are delegated to the canonical ARIA HTTP API.
"""

import json
import logging
from typing import Any

from mcp.errors import ToolInputError, require_repo, require_text, tool_boundary
from mcp.metadata import ToolMetadata

METADATA: list[ToolMetadata] = [
    ToolMetadata(
        name="query_codebase",
        display_name="Query Codebase (RAG)",
        description="Queries the codebase using RAG retrieval with confidence scoring and citation verification.",
        category="search",
        tags=["search", "rag", "query", "qa"],
        is_read_only=True,
        expected_latency="medium",
    ),
    ToolMetadata(
        name="semantic_search",
        display_name="Semantic Code Search",
        description="Performs vector similarity search across indexed code chunks.",
        category="search",
        tags=["search", "vector", "semantic", "embeddings"],
        is_read_only=True,
        expected_latency="fast",
    ),
]

logger = logging.getLogger("mcp.tools.search")


def register(server: Any) -> None:
    """Register search tools on the MCP server."""

    @server.tool()
    def query_codebase(owner: str, repo: str, query: str) -> str:
        """Queries the codebase using RAG with evaluation.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            query: The question or query to ask about the codebase.
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "query_codebase", {"owner": owner, "repo": repo, "query": query}
        ):
            with tool_boundary("query_codebase"):
                repo_name = require_repo(owner, repo)
                query_text = require_text("query", query)
                client = get_aria_client()
                result = client.post(
                    "/api/v1/retrieve",
                    json={"repo": repo_name, "question": query_text},
                )
                if isinstance(result, dict):
                    response = {
                        "answer": result.get("answer", ""),
                        "confidence": result.get("confidence", 0.0),
                        "sources": result.get("sources", []),
                        "verified": result.get("verified", False),
                    }
                else:
                    response = {
                        "answer": str(result),
                        "confidence": 0.0,
                        "sources": [],
                        "verified": False,
                    }
                return json.dumps(response, indent=2, default=str)

    @server.tool()
    def semantic_search(owner: str, repo: str, query: str, top_k: int = 10) -> str:
        """Performs semantic search across the codebase.

        Args:
            owner: Repository owner or organization name.
            repo: Repository name.
            query: The semantic search query.
            top_k: Number of results to return (default: 10).
        """
        from mcp.observability import mcp_request_context
        from mcp.dependencies import get_aria_client

        with mcp_request_context(
            "semantic_search",
            {"owner": owner, "repo": repo, "query": query, "top_k": top_k},
        ):
            with tool_boundary("semantic_search"):
                repo_name = require_repo(owner, repo)
                query_text = require_text("query", query)
                if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
                    raise ToolInputError(
                        "Invalid params: Argument 'top_k' must be a positive integer."
                    )
                client = get_aria_client()
                # Query retrieval endpoint and return the retrieved sources
                result = client.post(
                    "/api/v1/retrieve",
                    json={"repo": repo_name, "question": query_text},
                )
                sources = []
                if isinstance(result, dict):
                    sources = result.get("sources", [])[:top_k]
                return json.dumps(sources, indent=2, default=str)
