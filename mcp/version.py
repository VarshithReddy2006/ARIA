"""MCP Server Versioning and Build Metadata.

Centralized registry for server versioning, protocol compliance, build info,
and transport capability declarations.
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional

SERVER_NAME: str = "ARIA"
SERVER_VERSION: str = "1.5.0"
PROTOCOL_VERSION: str = "2024-11-05"
IMPLEMENTATION_NAME: str = "ria-mcp-server"
BUILD_VERSION: str = "1.5.0"

SUPPORTED_TRANSPORTS: List[str] = ["stdio", "sse"]
CAPABILITIES: List[str] = ["tools", "resources", "prompts", "logging"]


def get_git_commit() -> Optional[str]:
    """Retrieve the current Git commit hash if available."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def get_server_metadata() -> Dict[str, Any]:
    """Retrieve full server build and capability metadata."""
    return {
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "implementation_name": IMPLEMENTATION_NAME,
        "build_version": BUILD_VERSION,
        "git_commit": get_git_commit() or "unknown",
        "supported_transports": list(SUPPORTED_TRANSPORTS),
        "capabilities": list(CAPABILITIES),
    }
