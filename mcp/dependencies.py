"""MCP Service Resolution Bridge.

Exposes the unified AriaAPIClient for all MCP tools and resources.
Direct imports into backend.dependencies, ANALYSIS_STORE, SQLite, Chroma,
or LLM providers are strictly forbidden in the decoupled MCP architecture.
"""

from mcp.aria_client import AriaAPIClient, get_aria_client, set_aria_client

__all__ = [
    "AriaAPIClient",
    "get_aria_client",
    "set_aria_client",
]
