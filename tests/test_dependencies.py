"""Regression tests for backend analysis registry dependencies (Recovery Item R-004)."""

from backend.dependencies import analysis_registry


def test_analysis_registry_has_no_type_none_builders():
    """Assert that zero analysis capabilities are registered with type(None) as builder class."""
    type_none_entries = [
        name
        for name, node in analysis_registry.nodes.items()
        # Both operators are checked on purpose: ``is`` catches the plain
        # ``type(None)`` sentinel, while ``==`` also catches a registration whose
        # metaclass overrides ``__eq__``. Narrowing to ``is`` alone would weaken
        # the regression guard, so E721 is suppressed for this line only.
        if node.service_class is type(None) or node.service_class == type(None)  # noqa: E721
    ]

    assert len(type_none_entries) == 0, (
        f"Found analysis capabilities registered with type(None): {type_none_entries}"
    )
