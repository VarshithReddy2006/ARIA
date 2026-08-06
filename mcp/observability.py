"""MCP Observability Integration.

Bridges MCP tool invocations into the existing Observability Core,
reusing the same RequestContext, metrics_collector, and time_operation
infrastructure used by the REST API layer.

No new metrics backends or logging pipelines are created.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from core.observability.context import RequestContext
from core.observability.metrics import metrics_collector
from core.observability.timing import time_operation

logger = logging.getLogger("mcp.server")


@contextmanager
def mcp_request_context(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
) -> Generator[str, None, None]:
    """Establish observability context for an MCP tool invocation.

    Sets up RequestContext for request-ID correlation, records timing
    metrics, and emits structured log entries on entry and exit.

    Args:
        tool_name: The MCP tool being invoked.
        arguments: Tool arguments (logged at DEBUG, never at INFO to
            avoid leaking repository names or queries into production logs).

    Yields:
        The generated request ID for this invocation.
    """
    request_id = str(uuid.uuid4())
    start = time.time()

    logger.info(
        "MCP_TOOL_START tool=%s request_id=%s",
        tool_name,
        request_id,
    )
    if arguments:
        logger.debug(
            "MCP_TOOL_ARGS tool=%s request_id=%s args=%s",
            tool_name,
            request_id,
            arguments,
        )

    with RequestContext(request_id=request_id):
        with time_operation(f"mcp.tool.{tool_name}"):
            try:
                yield request_id
            except Exception as exc:
                elapsed = time.time() - start
                metrics_collector.increment_request("MCP", f"tools/{tool_name}", 500)
                metrics_collector.record_request_duration(
                    "MCP", f"tools/{tool_name}", 500, elapsed
                )
                logger.error(
                    "MCP_TOOL_ERROR tool=%s request_id=%s error=%s duration_ms=%.2f",
                    tool_name,
                    request_id,
                    str(exc),
                    elapsed * 1000,
                )
                raise
            else:
                elapsed = time.time() - start
                metrics_collector.increment_request("MCP", f"tools/{tool_name}", 200)
                metrics_collector.record_request_duration(
                    "MCP", f"tools/{tool_name}", 200, elapsed
                )
                logger.info(
                    "MCP_TOOL_COMPLETE tool=%s request_id=%s duration_ms=%.2f",
                    tool_name,
                    request_id,
                    elapsed * 1000,
                )
