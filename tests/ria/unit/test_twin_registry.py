"""Unit tests for TwinRegistry (Phase 11)."""

from __future__ import annotations


from ria.application.twin_registry import TwinRegistry


def test_twin_registry() -> None:
    reg = TwinRegistry()

    assert reg.builder_version().name == "default-twin-builder"
    assert reg.twin_version().twin_version == "1.0.0"
    assert "synchronization_engine" in reg.supported_capabilities()
