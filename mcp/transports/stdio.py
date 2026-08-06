"""Isolated Stdio Transport Adapter."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mcp.transports.stdio")


def run_stdio_transport(server: Any) -> None:
    """Run the FastMCP server over stdio transport."""
    logger.info("Initializing stdio transport execution...")
    server.run(transport="stdio")
