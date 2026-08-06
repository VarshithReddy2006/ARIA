"""Scope domain entity.

Represents a deterministic lexical scope hierarchy boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ria.domain.enums import ScopeKind
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourceSpan

__all__ = ["Scope"]


@dataclass(frozen=True)
class Scope:
    """Immutable representation of a lexical scope.

    Attributes:
        scope_id: Unique deterministic scope identity.
        kind: Scope category (module, class, function, block, etc.).
        name: Optional name for named scopes (function/class name).
        parent_id: Optional parent scope ID (None for root module scope).
        span: SourceSpan covered by this scope.
        language: Canonical language name.
    """

    scope_id: ScopeId
    kind: ScopeKind
    span: SourceSpan
    language: str
    name: Optional[str] = None
    parent_id: Optional[ScopeId] = None

    def __post_init__(self) -> None:
        if not self.language or not self.language.strip():
            raise ValueError("scope language must be non-empty")

    @property
    def is_root(self) -> bool:
        """Whether this scope is the root scope of a file."""
        return self.parent_id is None

    def __str__(self) -> str:
        name_str = f" {self.name}" if self.name else ""
        return f"scope:{self.kind.value}{name_str}"
