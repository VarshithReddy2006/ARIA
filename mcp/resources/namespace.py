"""Canonical Resource Namespace & Versioning Strategy.

Defines canonical URI builders, templates, and URI parsing rules for MCP resources.
Ensures stable public API URIs with reserved namespace versioning.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

RESOURCE_NAMESPACE_PREFIX: str = "repo://"
RESOURCE_API_VERSION: str = "v1"

# Canonical Resource URI Templates
TEMPLATE_REPOSITORIES: str = "repo://repositories"
TEMPLATE_METADATA: str = "repo://{owner}/{repo}/metadata"
TEMPLATE_ARCHITECTURE: str = "repo://{owner}/{repo}/architecture"
TEMPLATE_CALL_GRAPH: str = "repo://{owner}/{repo}/call-graph"
TEMPLATE_SYMBOLS: str = "repo://{owner}/{repo}/symbols"

# Regex pattern for parsing {owner}/{repo}/{resource_type}
_REPO_RESOURCE_REGEX = re.compile(
    r"^repo://(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<resource_type>metadata|architecture|call-graph|symbols)$"
)


def build_repositories_uri() -> str:
    """Build canonical URI for the repositories list resource."""
    return TEMPLATE_REPOSITORIES


def build_repo_resource_uri(owner: str, repo: str, resource_type: str) -> str:
    """Build canonical URI for a repository-specific resource."""
    return f"repo://{owner}/{repo}/{resource_type}"


def parse_resource_uri(uri: str) -> Optional[Dict[str, str]]:
    """Parse a resource URI into its constituent parameters.

    Returns dict with 'owner', 'repo', and 'resource_type', or None if URI
    is the root 'repo://repositories' or invalid.
    """
    if uri == TEMPLATE_REPOSITORIES:
        return {"resource_type": "repositories"}

    match = _REPO_RESOURCE_REGEX.match(uri)
    if match:
        return match.groupdict()
    return None
