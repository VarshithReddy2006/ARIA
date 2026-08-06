"""Namespace domain entity.

Represents a logical or file-system namespace container.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ria.domain.models.namespace_id import NamespaceId

__all__ = ["Namespace"]


@dataclass(frozen=True)
class Namespace:
    """Immutable representation of a namespace container.

    Attributes:
        namespace_id: Unique deterministic namespace identity.
        name: Name of the namespace.
        path: File path or logical package path.
        language: Canonical language name.
        parent_id: Optional parent namespace ID.
    """

    namespace_id: NamespaceId
    name: str
    path: str
    language: str
    parent_id: Optional[NamespaceId] = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("namespace name must be non-empty")
        if not self.language or not self.language.strip():
            raise ValueError("namespace language must be non-empty")

    def __str__(self) -> str:
        return f"namespace:{self.name}"
