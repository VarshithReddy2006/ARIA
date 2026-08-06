"""Symbol domain entity.

Represents a declared language entity bound to a scope, namespace, and location.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ria.domain.enums import DeclarationKind, Visibility
from ria.domain.models.declaration import Annotation, DocComment
from ria.domain.models.namespace_id import NamespaceId
from ria.domain.models.parser_identity import ParserFingerprint
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.span import SourceSpan
from ria.domain.models.symbol_id import SymbolId

__all__ = ["Symbol"]


@dataclass(frozen=True)
class Symbol:
    """Immutable representation of a semantic Symbol.

    Attributes:
        symbol_id: Unique deterministic identity.
        name: Short unqualified name.
        qualified_name: Fully qualified name within module or package.
        kind: Syntactic/semantic kind of declaration.
        language: Canonical language name.
        location: SourceSpan where the symbol is defined.
        visibility: Declared or inferred visibility.
        scope_id: Lexical scope where this symbol is declared.
        namespace_id: Optional namespace container ID.
        signature_text: Optional signature declaration string.
        documentation: Optional attached doc comment.
        annotations: Attached decorators or annotations.
        parser_fingerprint: Parser fingerprint that produced the parent AST.
    """

    symbol_id: SymbolId
    name: str
    qualified_name: str
    kind: DeclarationKind
    language: str
    location: SourceSpan
    visibility: Visibility
    scope_id: ScopeId
    parser_fingerprint: ParserFingerprint
    namespace_id: Optional[NamespaceId] = None
    signature_text: Optional[str] = None
    documentation: Optional[DocComment] = None
    annotations: Tuple[Annotation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("symbol name must be non-empty")
        if not self.qualified_name or not self.qualified_name.strip():
            raise ValueError("symbol qualified_name must be non-empty")
        if not self.language or not self.language.strip():
            raise ValueError("symbol language must be non-empty")
        object.__setattr__(self, "annotations", tuple(self.annotations))

    def __str__(self) -> str:
        return f"{self.qualified_name} ({self.kind.value})"
