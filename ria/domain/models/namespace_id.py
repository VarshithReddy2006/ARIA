"""Namespace identity value object.

Implements immutable, deterministic identity for namespaces and packages.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["NamespaceId"]


@dataclass(frozen=True)
class NamespaceId:
    """Immutable identity of a namespace container.

    Attributes:
        value: String representation of the namespace identity.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("namespace_id value must be non-empty")

    @classmethod
    def for_namespace(
        cls,
        language: str,
        path: str,
        qualified_name: str,
    ) -> NamespaceId:
        """Construct a deterministic NamespaceId.

        Args:
            language: Canonical language name.
            path: Normalised repository-relative path or package path.
            qualified_name: Qualified name of the namespace.

        Returns:
            A NamespaceId instance.
        """
        return cls(value=f"ns:{language}:{path}:{qualified_name}")

    def __str__(self) -> str:
        return self.value
