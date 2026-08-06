"""Automated Safe Tool Module Discovery.

Dynamically discovers, imports, and registers tool modules from the mcp.tools
package in deterministic alphabetical order. Fault-isolated to prevent a single
failing module from breaking the entire server.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, List

from mcp.metadata import register_tool_metadata, ToolMetadata

logger = logging.getLogger("mcp.tools.discovery")


def discover_and_register_tools(server: Any) -> List[str]:
    """Automatically discover and register all tool modules under mcp.tools.

    Scans the mcp.tools package for modules containing a callable `register(server)`
    function. Module registration proceeds in strict alphabetical order.

    Args:
        server: The FastMCP server instance.

    Returns:
        List of successfully registered tool module names.
    """
    import mcp.tools

    package_path = mcp.tools.__path__
    package_prefix = mcp.tools.__name__ + "."

    registered_modules: List[str] = []

    # 1. Discover all module names under mcp.tools
    module_names: List[str] = []
    for _, module_name, is_pkg in pkgutil.iter_modules(package_path, package_prefix):
        if not is_pkg:
            module_names.append(module_name)

    # 2. Sort deterministically (alphabetical order)
    module_names.sort()

    # 3. Import and register each module safely
    for module_name in module_names:
        short_name = module_name.split(".")[-1]

        # Skip private/dunder or init modules
        if short_name.startswith("_"):
            continue

        try:
            mod = importlib.import_module(module_name)

            # Check if module exposes a callable `register` function
            register_fn = getattr(mod, "register", None)
            if register_fn is None or not callable(register_fn):
                logger.debug(
                    "Skipping module '%s': no callable 'register(server)' function found",
                    module_name,
                )
                continue

            # Register tools on server
            register_fn(server)

            # Register metadata if exposed by module
            metadata_list = getattr(mod, "METADATA", [])
            if isinstance(metadata_list, list):
                for meta in metadata_list:
                    if isinstance(meta, ToolMetadata):
                        register_tool_metadata(meta)

            registered_modules.append(short_name)
            logger.info("Successfully registered MCP tool module '%s'", short_name)

        except Exception as exc:
            logger.error(
                "Failed to register MCP tool module '%s': %s",
                module_name,
                exc,
                exc_info=True,
            )

    return registered_modules
