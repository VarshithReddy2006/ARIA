"""MCP Server Package for Repo Intelligence Agent.

Exposes the Repository Intelligence Platform's analysis engines through
the Model Context Protocol (MCP), enabling integration with VS Code,
Cursor, Claude Desktop, and AI coding agents.

This package is a thin integration layer — all business logic is
delegated to existing services via backend/dependencies.py.
"""

__all__ = ["create_server"]
