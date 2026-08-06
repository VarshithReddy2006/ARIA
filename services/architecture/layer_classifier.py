"""Architecture Layer Classifier.

Classifies a module or file path into 9 canonical architectural layers:
  - Presentation (UI, React components, Astro views)
  - Application (orchestrators, use-cases, pipelines)
  - Domain (models, business entities, value objects)
  - Infrastructure (database, HTTP clients, external services, caches)
  - Data (schemas, repositories, storage interfaces)
  - Integration (third-party SDKs, API connectors, webhooks)
  - Shared (utils, helpers, core constants)
  - Test (unit tests, integration test suites, mocks)
  - Configuration (settings, environment configs, build configs)
"""

from __future__ import annotations

import os
from typing import Literal

ArchitectureLayer = Literal[
    "Presentation",
    "Application",
    "Domain",
    "Infrastructure",
    "Data",
    "Integration",
    "Shared",
    "Test",
    "Configuration",
]


def classify_layer(path: str, category: str = "", content_snippet: str = "") -> ArchitectureLayer:
    """Determine the architectural layer of a file or module based on path rules and content."""
    clean_path = path.replace("\\", "/").lower()
    base_name = os.path.basename(clean_path)

    # Test layer
    if (
        "test" in clean_path
        or "spec" in clean_path
        or base_name.startswith("test_")
        or base_name.endswith("_test.py")
        or base_name.endswith(".spec.ts")
        or base_name.endswith(".test.tsx")
    ):
        return "Test"

    # Configuration layer
    if (
        "config" in clean_path
        or "setting" in clean_path
        or base_name in ("pyproject.toml", "package.json", "tsconfig.json", "dockerfile", ".env")
        or base_name.endswith(".config.js")
        or base_name.endswith(".config.ts")
    ):
        return "Configuration"

    # Presentation layer (UI components, React, views, routes)
    if (
        "component" in clean_path
         or "view" in clean_path
         or "page" in clean_path
         or "ui" in clean_path
         or clean_path.endswith(".tsx")
         or clean_path.endswith(".jsx")
         or clean_path.endswith(".astro")
         or "frontend/" in clean_path
    ):
        return "Presentation"

    # Presentation / Controller via router
    if "router" in clean_path or "endpoint" in clean_path or "controller" in clean_path:
        return "Presentation"

    # Infrastructure / Integration layer
    if (
        "infra" in clean_path
        or "client" in clean_path
        or "adapter" in clean_path
        or "provider" in clean_path
        or "http" in clean_path
        or "sdk" in clean_path
        or "mcp" in clean_path
    ):
        return "Infrastructure"

    # Domain layer
    if (
        "domain" in clean_path
        or "entity" in clean_path
        or "model" in clean_path
        or "types.ts" in clean_path
        or "schemas.py" in clean_path
    ):
        return "Domain"

    # Data layer
    if (
        "db" in clean_path
        or "database" in clean_path
        or "repo" in clean_path
        or "storage" in clean_path
        or "store" in clean_path
        or "schema" in clean_path
    ):
        return "Data"

    # Application layer
    if (
        "service" in clean_path
        or "pipeline" in clean_path
        or "orchestrat" in clean_path
        or "usecase" in clean_path
        or "handler" in clean_path
    ):
        return "Application"

    # Shared layer
    if "util" in clean_path or "helper" in clean_path or "common" in clean_path or "shared" in clean_path:
        return "Shared"

    # Fallback by category label if available
    if category == "entry_point":
        return "Presentation"
    if category == "core_module":
        return "Application"

    return "Domain"
