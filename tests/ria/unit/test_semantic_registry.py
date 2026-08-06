"""Unit tests for SemanticRegistry (Phase 10 & 14)."""

from __future__ import annotations

import pytest

from ria.application.semantic_registry import SemanticRegistry
from ria.application.semantic_service import SemanticResolutionService


def test_semantic_registry() -> None:
    registry = SemanticRegistry()
    service = SemanticResolutionService()

    registry.register_resolver("python", service)
    assert registry.get_resolver("python") == service
    assert "python" in registry.supported_languages()

    with pytest.raises(ValueError, match="already registered"):
        registry.register_resolver("python", service)
