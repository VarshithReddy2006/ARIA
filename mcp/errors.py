"""Client-visible error semantics for the FastMCP tool layer.

Mirrors ``backend/mcp_server.py`` so both MCP implementations behave identically
from a client's point of view.

Why raising is correct here
---------------------------
FastMCP owns the JSON-RPC envelope. When a tool function raises, the SDK
converts the exception into a ``CallToolResult`` with ``isError=True``
(``mcp/server/fastmcp/tools/base.py`` wraps it in ``ToolError``, and
``mcp/server/lowlevel/server.py`` sets ``isError=True``). That is the
MCP-compliant way to report a business failure, and it is what the legacy
stdio server emits by hand. Returning ``{"error": ...}`` from a tool instead
produces a *successful* result whose payload merely looks like an error, which
no compliant client can distinguish from real data.

The SDK's wrapper interpolates ``str(exception)`` directly into the message, so
redaction has to happen before the exception escapes the tool body. That is what
:func:`tool_boundary` is for. The redaction predicates are imported from the
legacy module rather than reimplemented, so there is exactly one definition of
what is safe to disclose.
"""

from __future__ import annotations

import logging
import traceback
from contextlib import contextmanager
from typing import Any, Iterator

from backend.mcp_server import _client_safe_message, _debug_errors_enabled

logger = logging.getLogger("mcp.errors")

__all__ = [
    "ToolInputError",
    "ToolFailure",
    "require_text",
    "require_repo",
    "tool_boundary",
]


class ToolInputError(ValueError):
    """Arguments failed contract validation.

    The legacy server maps this condition to JSON-RPC ``-32602``. FastMCP cannot
    emit a JSON-RPC error from inside a tool body, so this surfaces as an
    ``isError`` result instead. The *message* text is kept identical to the
    legacy wording so clients see the same diagnostics either way.
    """


class ToolFailure(RuntimeError):
    """A business failure whose message has already been made client-safe."""


def require_text(name: str, value: Any) -> str:
    """Validate and normalise a required string argument.

    Applies the same rules, in the same order, with the same messages as
    ``validate_tool_arguments`` in the legacy server: presence, then type, then
    non-emptiness after trimming. Returns the trimmed value.
    """
    if value is None:
        raise ToolInputError(f"Invalid params: Missing required argument(s): {name}.")
    if not isinstance(value, str):
        raise ToolInputError(
            f"Invalid params: Argument '{name}' must be a string, "
            f"got {type(value).__name__}."
        )
    trimmed = value.strip()
    if not trimmed:
        raise ToolInputError(f"Invalid params: Argument '{name}' must not be empty.")
    return trimmed


def require_repo(owner: Any, repo: Any) -> str:
    """Validate the owner/repo pair and return the canonical ``owner/repo`` key.

    Centralised because every repository-scoped tool needs it, and because the
    legacy server's failure mode for a blank owner ("repository '/' is not
    indexed") was actively misleading.
    """
    return f"{require_text('owner', owner)}/{require_text('repo', repo)}"


@contextmanager
def tool_boundary(tool_name: str) -> Iterator[None]:
    """Log the full exception internally; re-raise a redacted one for the client.

    ``ToolInputError`` and :class:`ToolFailure` messages are already curated, so
    they pass through untouched. Anything else is unplanned and may embed paths,
    SQL, or internal identifiers, so it is replaced with a fixed string. The full
    traceback always reaches the server log, and reaches the client only when
    ``MCP_DEBUG_ERRORS`` is set, matching the legacy server's debug gate.
    """
    try:
        yield
    except (ToolInputError, ToolFailure) as safe:
        logger.warning("Tool %s rejected or failed: %s", tool_name, safe)
        raise
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
        message = _client_safe_message(tool_name, exc)
        if _debug_errors_enabled():
            message = f"{message}\n\n{traceback.format_exc()}"
        raise ToolFailure(message) from None
