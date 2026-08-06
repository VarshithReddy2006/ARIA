"""TEST HARNESS ONLY — not a production entry point.

`backend.cli mcp` starts the stdio MCP server without ever calling
`_load_analysis_store()`, so `ANALYSIS_STORE` stays empty and every
repository-scoped tool fails with "not indexed" (see BUG-001).

This launcher hydrates the store first, then starts the identical server loop.
It exists so the validator can exercise real happy paths and prove that the
missing hydration call is the sole cause of those failures. Do not ship it and
do not treat it as the fix; the fix belongs in the production startup path.

    python scripts/mcp_validate.py --launch-module scripts.mcp_hydrated_launcher
"""

from backend.dependencies import _load_analysis_store
from backend.mcp_server import run_mcp_server

if __name__ == "__main__":
    _load_analysis_store()
    run_mcp_server()
