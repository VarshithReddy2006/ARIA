"""Standardized Tool Metadata Model & Registry.

Defines the ToolMetadata schema and provides global registry aggregation
for self-describing MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ToolMetadata:
    """Metadata describing an MCP tool's operational characteristics."""

    name: str
    display_name: str
    description: str
    category: str  # "repository", "architecture", "symbol", "search", "analysis", "workspace", "report"
    tags: List[str] = field(default_factory=list)
    is_read_only: bool = True
    expected_latency: str = "fast"  # "fast", "medium", "slow"
    supports_streaming: bool = False
    is_experimental: bool = False
    is_deprecated: bool = False


# Global registry mapping tool_name -> ToolMetadata
TOOL_METADATA_REGISTRY: Dict[str, ToolMetadata] = {}


def register_tool_metadata(metadata: ToolMetadata) -> None:
    """Register a tool's metadata in the global registry."""
    TOOL_METADATA_REGISTRY[metadata.name] = metadata


def get_tool_metadata(tool_name: str) -> Optional[ToolMetadata]:
    """Retrieve metadata for a specific tool by name."""
    return TOOL_METADATA_REGISTRY.get(tool_name)


def list_all_tool_metadata() -> List[ToolMetadata]:
    """Retrieve all registered tool metadata entries."""
    return list(TOOL_METADATA_REGISTRY.values())
