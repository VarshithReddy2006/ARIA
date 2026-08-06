# MCP SDK Migration & Pydantic Compatibility Guide (v1.5.0)

This guide documents the SDK compatibility policies, Pydantic constraints, and migration paths for the **Production MCP Integration Layer** of the Repository Intelligence Agent (v1.5.0 Production Release).

---

## Overview

The Production MCP Integration Layer runs within the **Repository Intelligence Architecture (RIA v1)** and exposes repository intelligence over standard JSON-RPC 2.0 frames.

The platform implements a dual-server architecture:
1. **Legacy MCP Server** (`backend/mcp_server.py`): Lightweight stdio server with zero external SDK dependencies.
2. **FastMCP Server** (`mcp/server.py`): FastMCP SDK integration for automatic tool discovery, resource templates, prompt templates, and SSE transport.

---

## Dependency Bounding & Pydantic Policy

To preserve runtime stability across SDK updates, dependencies are strictly bounded in `pyproject.toml` and `requirements.txt`:

```toml
[project]
dependencies = [
    "pydantic<2.7.0",
    "mcp[cli]<2.0.0",
]
```

### Rationale
- **FastMCP 1.x Compatibility**: FastMCP 1.x relies on `pydantic.create_model()` signature conventions. Pydantic versions `>=2.7.0` changed internal kwarg reflection schemas, triggering runtime validation exceptions during server startup.
- **SDK 2.x Migration Protection**: FastMCP SDK 2.x refactored module namespaces (`mcp.server.fastmcp`). Bounding `mcp[cli]<2.0.0` prevents auto-upgrade breakage until SDK 2.x migration is formally certified.

---

## Migration Path to SDK 2.x

When upgrading to SDK 2.x in future releases:
1. Update `pyproject.toml` dependency specifier to `mcp[cli]>=2.0.0`.
2. Update imports in `mcp/server.py` to point to the official FastMCP 2.x module.
3. Validate Pydantic 2.7+ schema creation via `tests/test_mcp_sdk_compatibility.py`.
4. Run full transport integration suite `pytest tests/test_mcp_transport_stdio.py -v`.
