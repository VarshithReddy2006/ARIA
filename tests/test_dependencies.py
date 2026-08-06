"""Regression tests for backend analysis registry dependencies (Recovery Item R-004)."""

from backend.dependencies import analysis_registry


def test_analysis_registry_has_no_type_none_builders():
    """Assert that zero analysis capabilities are registered with type(None) as builder class."""
    type_none_entries = [
        name
        for name, node in analysis_registry.nodes.items()
        if node.service_class is type(None) or node.service_class == type(None)
    ]

    assert (
        len(type_none_entries) == 0
    ), f"Found analysis capabilities registered with type(None): {type_none_entries}"
