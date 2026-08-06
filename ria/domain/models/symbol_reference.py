"""Symbol reference domain entities.

Represents references/uses of symbols across scopes and files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ria.domain.enums import ReferenceKind
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourceSpan
from ria.domain.models.symbol_id import SymbolId

__all__ = ["ReferenceTarget", "SymbolReference"]


@dataclass(frozen=True)
class ReferenceTarget:
    """Immutable target of a symbol reference.

    Attributes:
        target_name: Identifier or qualified name being referenced.
        target_symbol_id: Resolved target SymbolId, or None if unresolved.
        is_resolved: Whether the reference resolved to a known symbol.
        module_moniker: Optional moniker of the imported target module.
    """

    target_name: str
    target_symbol_id: Optional[SymbolId] = None
    is_resolved: bool = False
    module_moniker: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.target_name or not self.target_name.strip():
            raise ValueError("target_name must be non-empty")
        if self.target_symbol_id is not None and not self.is_resolved:
            object.__setattr__(self, "is_resolved", True)

    def with_resolved(self, target_symbol_id: SymbolId) -> ReferenceTarget:
        """Return a copy of this target bound to a resolved SymbolId."""
        return ReferenceTarget(
            target_name=self.target_name,
            target_symbol_id=target_symbol_id,
            is_resolved=True,
            module_moniker=self.module_moniker,
        )


@dataclass(frozen=True)
class SymbolReference:
    """Immutable occurrence of a symbol reference in source code.

    Attributes:
        span: SourceSpan where the reference occurs.
        scope_id: Lexical scope where the reference appears.
        target: ReferenceTarget describing the referenced entity.
        kind: ReferenceKind (read, write, call, import, etc.).
        location_file_path: Normalised file path containing the reference.
        source_symbol_id: Optional enclosing SymbolId (e.g. caller function/method).
    """

    span: SourceSpan
    scope_id: ScopeId
    target: ReferenceTarget
    kind: ReferenceKind
    location_file_path: str
    source_symbol_id: Optional[SymbolId] = None

    def __post_init__(self) -> None:
        if not self.location_file_path or not self.location_file_path.strip():
            raise ValueError("location_file_path must be non-empty")

    def __str__(self) -> str:
        res_str = (
            f"-> {self.target.target_symbol_id}"
            if self.target.is_resolved
            else "(unresolved)"
        )
        return f"ref:{self.kind.value} {self.target.target_name} {res_str}"
