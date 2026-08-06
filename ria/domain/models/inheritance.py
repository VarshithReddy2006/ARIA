"""Inheritance and override relationship domain models.

Represents subtyping, interface implementation, trait application, and method overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ria.domain.enums import InheritanceKind
from ria.domain.models.span import SourceSpan
from ria.domain.models.symbol_id import SymbolId

__all__ = ["InheritanceRelation", "OverrideRelation"]


@dataclass(frozen=True)
class InheritanceRelation:
    """Immutable subtyping relationship between types.

    Attributes:
        child_symbol_id: SymbolId of the subclass / implementing type.
        parent_name: Name of the base class / interface / trait being extended.
        kind: InheritanceKind (extends, implements, inherits, mixin, trait).
        span: SourceSpan where the inheritance clause appears.
        parent_symbol_id: Resolved parent SymbolId, or None if unresolved/external.
    """

    child_symbol_id: SymbolId
    parent_name: str
    kind: InheritanceKind
    span: SourceSpan
    parent_symbol_id: Optional[SymbolId] = None

    def __post_init__(self) -> None:
        if not self.parent_name or not self.parent_name.strip():
            raise ValueError("parent_name must be non-empty")

    @property
    def is_resolved(self) -> bool:
        """Whether the parent type was resolved to a known symbol."""
        return self.parent_symbol_id is not None

    def with_resolved_parent(self, parent_symbol_id: SymbolId) -> InheritanceRelation:
        """Return a copy with parent_symbol_id set."""
        return InheritanceRelation(
            child_symbol_id=self.child_symbol_id,
            parent_name=self.parent_name,
            kind=self.kind,
            span=self.span,
            parent_symbol_id=parent_symbol_id,
        )


@dataclass(frozen=True)
class OverrideRelation:
    """Immutable method override relationship.

    Attributes:
        overriding_symbol_id: SymbolId of the method doing the overriding.
        overridden_symbol_id: SymbolId of the method being overridden.
        overridden_name: Name of the overridden method.
        span: SourceSpan of the overriding method declaration.
    """

    overriding_symbol_id: SymbolId
    overridden_symbol_id: SymbolId
    overridden_name: str
    span: SourceSpan

    def __post_init__(self) -> None:
        if not self.overridden_name or not self.overridden_name.strip():
            raise ValueError("overridden_name must be non-empty")
