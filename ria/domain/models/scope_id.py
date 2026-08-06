"""Scope identity value object.

Implements immutable, deterministic identity for lexical scopes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from ria.domain.enums import ScopeKind
from ria.domain.models.span import SourceSpan

__all__ = ["ScopeId"]


@dataclass(frozen=True)
class ScopeId:
    """Immutable identity of a lexical scope.

    Attributes:
        value: String representation of the scope identity.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("scope_id value must be non-empty")

    @classmethod
    def for_scope(
        cls,
        language: str,
        file_path: str,
        scope_kind: ScopeKind,
        name: Optional[str],
        span: SourceSpan,
    ) -> ScopeId:
        """Construct a deterministic ScopeId.

        Args:
            language: Canonical language name.
            file_path: Normalised repository-relative path.
            scope_kind: Category of the scope.
            name: Optional scope name.
            span: SourceSpan defining scope boundaries.

        Returns:
            A deterministic ScopeId instance.
        """
        name_part = name or "<anonymous>"
        raw_key = f"{language}:{file_path}:{scope_kind.value}:{name_part}:{span.start.line}:{span.start.column}-{span.end.line}:{span.end.column}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
        return cls(
            value=f"scope:{language}:{file_path}:{scope_kind.value}:{name_part}:{digest}"
        )

    @classmethod
    def root(cls, language: str, file_path: str) -> ScopeId:
        """Construct a root module scope ID for a file.

        Args:
            language: Canonical language name.
            file_path: Normalised repository-relative path.

        Returns:
            Root module ScopeId instance.
        """
        return cls(value=f"scope:{language}:{file_path}:root")

    def __str__(self) -> str:
        return self.value
