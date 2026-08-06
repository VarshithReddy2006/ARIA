"""MCP Transport Adapters.

Provides isolated transport execution logic for stdio and sse transports.
Transports are limited to connection framing and protocol delegation;
they never access domain services directly.
"""

from mcp.transports.stdio import run_stdio_transport
from mcp.transports.sse import run_sse_transport

__all__ = ["run_stdio_transport", "run_sse_transport"]
