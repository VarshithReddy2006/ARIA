"""SQLite implementation of SemanticCacheStore port.

Implements :class:`~ria.ports.semantic.SemanticCacheStore` over SQLite connections.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.enums import (
    DeclarationKind,
    DiagnosticSeverity,
    ScopeKind,
    Visibility,
)
from ria.domain.errors import StorageError
from ria.domain.models.namespace_id import NamespaceId
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.scope import Scope
from ria.domain.models.scope_id import ScopeId
from ria.domain.models.semantic_identity import SemanticCacheKey, SemanticFingerprint
from ria.domain.models.semantic_result import (
    ResolutionDiagnostic,
    ResolutionResult,
)
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.symbol import Symbol
from ria.domain.models.symbol_id import SymbolId
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.semantic import SemanticCacheStore

__all__ = ["SqliteSemanticCacheStore"]


class SqliteSemanticCacheStore(SemanticCacheStore):
    """Durable SQLite semantic cache store."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: SemanticCacheKey) -> Optional[ResolutionResult]:
        """Retrieve a cached ResolutionResult by SemanticCacheKey."""
        digest = key.digest()
        conn = self._connections.connection()
        try:
            row = conn.execute(
                "SELECT reuse_key, result_json, cached_at FROM ria_semantic_cache WHERE cache_key_digest = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return None

            data = json.loads(row["result_json"])
            result = _deserialize_resolution_result(data)
            object.__setattr__(result, "from_cache", True)
            return result
        except Exception as exc:
            raise StorageError(f"failed to read semantic cache entry: {exc}") from exc

    def put(self, key: SemanticCacheKey, result: ResolutionResult) -> None:
        """Store a ResolutionResult in the semantic cache."""
        digest = key.digest()
        reuse_key = key.reuse_key
        language = key.language
        fp_digest = key.fingerprint.digest()
        fp_token = key.fingerprint.token()
        result_json = json.dumps(_serialize_resolution_result(result))
        cached_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_semantic_cache
                (cache_key_digest, reuse_key, language, fingerprint_digest, fingerprint_token, result_json, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET
                    result_json = excluded.result_json,
                    cached_at = excluded.cached_at
                """,
                (
                    digest,
                    reuse_key,
                    language,
                    fp_digest,
                    fp_token,
                    result_json,
                    cached_at,
                ),
            )
        except Exception as exc:
            raise StorageError(f"failed to write semantic cache entry: {exc}") from exc

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        """Purge cached entries matching reuse_key."""
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_semantic_cache WHERE reuse_key = ?",
                (reuse_key,),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate semantic cache by reuse_key: {exc}"
            ) from exc

    def invalidate_by_fingerprint(self, fingerprint: SemanticFingerprint) -> int:
        """Purge cached entries produced under fingerprint."""
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_semantic_cache WHERE fingerprint_digest = ?",
                (fingerprint.digest(),),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate semantic cache by fingerprint: {exc}"
            ) from exc

    def clear(self) -> None:
        """Purge all entries from the semantic cache."""
        conn = self._connections.connection()
        try:
            conn.execute("DELETE FROM ria_semantic_cache")
        except Exception as exc:
            raise StorageError(f"failed to clear semantic cache: {exc}") from exc


# -- Serialization Helpers -------------------------------------------------


def _serialize_span(s: SourceSpan) -> Dict[str, Any]:
    return {
        "start": {"byte": s.start.byte, "line": s.start.line, "column": s.start.column},
        "end": {"byte": s.end.byte, "line": s.end.line, "column": s.end.column},
    }


def _deserialize_span(d: Dict[str, Any]) -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(**d["start"]),
        end=SourcePosition(**d["end"]),
    )


def _serialize_resolution_result(res: ResolutionResult) -> Dict[str, Any]:
    return {
        "symbols": [
            {
                "symbol_id": s.symbol_id.value,
                "name": s.name,
                "qualified_name": s.qualified_name,
                "kind": s.kind.value,
                "language": s.language,
                "location": _serialize_span(s.location),
                "visibility": s.visibility.value,
                "scope_id": s.scope_id.value,
                "namespace_id": s.namespace_id.value if s.namespace_id else None,
                "signature_text": s.signature_text,
            }
            for s in res.symbols
        ],
        "scopes": [
            {
                "scope_id": sc.scope_id.value,
                "kind": sc.kind.value,
                "span": _serialize_span(sc.span),
                "language": sc.language,
                "name": sc.name,
                "parent_id": sc.parent_id.value if sc.parent_id else None,
            }
            for sc in res.scopes
        ],
        "diagnostics": [
            {
                "severity": d.severity.value,
                "message": d.message,
                "code": d.code,
            }
            for d in res.diagnostics
        ],
        "from_cache": res.from_cache,
    }


def _deserialize_resolution_result(data: Dict[str, Any]) -> ResolutionResult:
    fp_dummy = ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("extractor", "1.0.0"),
        language=ComponentVersion("lang", "1.0.0"),
    )

    symbols = [
        Symbol(
            symbol_id=SymbolId(s["symbol_id"]),
            name=s["name"],
            qualified_name=s["qualified_name"],
            kind=DeclarationKind(s["kind"]),
            language=s["language"],
            location=_deserialize_span(s["location"]),
            visibility=Visibility(s["visibility"]),
            scope_id=ScopeId(s["scope_id"]),
            namespace_id=NamespaceId(s["namespace_id"])
            if s.get("namespace_id")
            else None,
            signature_text=s.get("signature_text"),
            parser_fingerprint=fp_dummy,
        )
        for s in data.get("symbols", [])
    ]

    scopes = [
        Scope(
            scope_id=ScopeId(sc["scope_id"]),
            kind=ScopeKind(sc["kind"]),
            span=_deserialize_span(sc["span"]),
            language=sc["language"],
            name=sc.get("name"),
            parent_id=ScopeId(sc["parent_id"]) if sc.get("parent_id") else None,
        )
        for sc in data.get("scopes", [])
    ]

    diagnostics = [
        ResolutionDiagnostic(
            severity=DiagnosticSeverity(d["severity"]),
            message=d["message"],
            code=d.get("code", "SEMANTIC_ERROR"),
        )
        for d in data.get("diagnostics", [])
    ]

    return ResolutionResult(
        symbols=tuple(symbols),
        scopes=tuple(scopes),
        diagnostics=tuple(diagnostics),
        from_cache=data.get("from_cache", True),
    )
