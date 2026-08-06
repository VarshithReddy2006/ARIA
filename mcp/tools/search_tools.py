"""Search MCP Tools.

Exposes codebase querying and semantic search.
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
        from mcp.dependencies import get_retrieval_service

        with mcp_request_context(
            "query_codebase", {"owner": owner, "repo": repo, "query": query}
        ):
            with tool_boundary("query_codebase"):
                repo_name = require_repo(owner, repo)
                query = require_text("query", query)
                service = get_retrieval_service()
                # RetrievalService's public entry point is retrieve_and_answer();
                # this matches the validated legacy stdio server exactly.
                result = service.retrieve_and_answer(repo_name, query)
                if isinstance(result, dict):
                    answer = result.get("answer", "")
                    confidence = result.get("confidence", 0.0)
                    sources = [
                        s.model_dump() if hasattr(s, "model_dump") else s
                        for s in result.get("sources", [])
                    ]
                    verified = result.get("verified", False)
                else:
                    answer = getattr(result, "answer", "")
                    confidence = getattr(result, "confidence", 0.0)
                    sources = [
                        s.model_dump() if hasattr(s, "model_dump") else s
                        for s in getattr(result, "sources", [])
                    ]
                    verified = getattr(result, "verified", False)

                response = {
                    "answer": answer,
                    "confidence": confidence,
                    "sources": sources,
                    "verified": verified,
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
        from mcp.dependencies import get_chroma_store, get_embedding_service

        with mcp_request_context(
            "semantic_search",
            {"owner": owner, "repo": repo, "query": query, "top_k": top_k},
        ):
            with tool_boundary("semantic_search"):
                repo_name = require_repo(owner, repo)
                query = require_text("query", query)
                if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
                    raise ToolInputError(
                        "Invalid params: Argument 'top_k' must be a positive integer."
                    )
                # StructuralRetrievalEngine.search() never existed, and its
                # retrieve() replacement takes a policy rather than a top_k and
                # returns an assembled context. Embedding the query and hitting
                # the vector store directly is the same two-step the chat
                # retrieval path uses (services/chat/retrieval.py) and is the only
                # route that honours this tool's advertised top_k contract.
                query_embedding = get_embedding_service().generate_embedding(query)
                results = get_chroma_store().search_repository(
                    repo_name, query_embedding, limit=top_k
                )
                serialized = [
                    r.model_dump() if hasattr(r, "model_dump") else r for r in results
                ]
                return json.dumps(serialized, indent=2, default=str)
