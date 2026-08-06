"""Isolated SSE Transport Adapter."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mcp.transports.sse")


def run_sse_transport(server: Any, host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the FastMCP server over SSE (Server-Sent Events) transport."""
    logger.info("Initializing SSE transport execution on %s:%d...", host, port)
    # Delegates to FastMCP's SSE runner if supported
    if hasattr(server, "run") and callable(server.run):
        server.run(transport="sse")
    else:
        raise NotImplementedError(
            "SSE transport is not supported by the current server instance"
        )
