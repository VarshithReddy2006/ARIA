"""SQLite implementation of ParseCacheStore port.

Implements :class:`~ria.ports.parser.ParseCacheStore` over SQLite connections.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.enums import (
    DeclarationKind,
    DiagnosticSeverity,
    ParserCapability,
    Visibility,
)
from ria.domain.errors import StorageError
from ria.domain.identity import ContentHash
from ria.domain.models.declaration import Annotation, DocComment, SyntaxDeclaration
from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parse_result import (
    ParseDiagnostic,
    ParseResult,
    ParseTiming,
)
from ria.domain.models.parser_identity import (
    ComponentVersion,
    ParseCacheKey,
    ParserFingerprint,
)
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_facts import (
    CommentBlock,
    ExportStatement,
    ExtractedSyntax,
    ImportedName,
    ImportStatement,
)
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.parser import ParseCacheStore

__all__ = ["SqliteParseCacheStore"]


class SqliteParseCacheStore(ParseCacheStore):
    """Durable SQLite parse cache store.

    Stores and retrieves ParseCacheEntry records.
    """

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: ParseCacheKey) -> Optional[ParseCacheEntry]:
        """Retrieve a cached parse result by ParseCacheKey."""
        digest = key.digest()
        conn = self._connections.connection()
        try:
            row = conn.execute(
                "SELECT reuse_key, result_json, cached_at FROM ria_parse_cache WHERE cache_key_digest = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return None

            data = json.loads(row["result_json"])
            cached_at = datetime.fromisoformat(row["cached_at"])
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)

            result = _deserialize_parse_result(data)
            return ParseCacheEntry(key=key, result=result, cached_at=cached_at)
        except Exception as exc:
            raise StorageError(f"failed to read parse cache entry: {exc}") from exc

    def put(self, entry: ParseCacheEntry) -> None:
        """Store a ParseCacheEntry in the parse cache."""
        digest = entry.key.digest()
        reuse_key = entry.key.reuse_key
        language = entry.result.language
        fp_digest = entry.key.fingerprint.digest()
        fp_token = entry.key.fingerprint.token()
        result_json = json.dumps(_serialize_parse_result(entry.result))
        cached_at = entry.cached_at.isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_parse_cache
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
            raise StorageError(f"failed to write parse cache entry: {exc}") from exc

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        """Invalidate all cached entries matching reuse_key."""
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_parse_cache WHERE reuse_key = ?",
                (reuse_key,),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate parse cache by reuse_key: {exc}"
            ) from exc

    def invalidate_by_fingerprint(self, fingerprint: ParserFingerprint) -> int:
        """Invalidate all cached entries produced under fingerprint."""
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_parse_cache WHERE fingerprint_digest = ?",
                (fingerprint.digest(),),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate parse cache by fingerprint: {exc}"
            ) from exc

    def clear(self) -> None:
        """Purge all entries from the parse cache."""
        conn = self._connections.connection()
        try:
            conn.execute("DELETE FROM ria_parse_cache")
        except Exception as exc:
            raise StorageError(f"failed to clear parse cache: {exc}") from exc


# -- Serialization Helpers -------------------------------------------------


def _serialize_parse_result(res: ParseResult) -> Dict[str, Any]:
    return {
        "reuse_key": res.reuse_key,
        "language": res.language,
        "fingerprint": {
            "parser": {
                "name": res.fingerprint.parser.name,
                "version": res.fingerprint.parser.version,
            },
            "extractor": {
                "name": res.fingerprint.extractor.name,
                "version": res.fingerprint.extractor.version,
            },
            "language": {
                "name": res.fingerprint.language.name,
                "version": res.fingerprint.language.version,
            },
        },
        "tree": _serialize_tree(res.tree) if res.tree is not None else None,
        "extracted": _serialize_extracted(res.extracted),
        "diagnostics": [_serialize_diagnostic(d) for d in res.diagnostics],
        "timing": {
            "parse_seconds": res.timing.parse_seconds,
            "extract_seconds": res.timing.extract_seconds,
        },
        "capabilities": [c.value for c in res.capabilities],
        "from_cache": res.from_cache,
    }


def _deserialize_parse_result(data: Dict[str, Any]) -> ParseResult:
    fp_data = data["fingerprint"]
    fp = ParserFingerprint(
        parser=ComponentVersion(**fp_data["parser"]),
        extractor=ComponentVersion(**fp_data["extractor"]),
        language=ComponentVersion(**fp_data["language"]),
    )
    tree = _deserialize_tree(data["tree"]) if data.get("tree") is not None else None
    extracted = _deserialize_extracted(data.get("extracted", {}))
    diagnostics = tuple(_deserialize_diagnostic(d) for d in data.get("diagnostics", []))
    timing = ParseTiming(**data.get("timing", {}))
    capabilities = frozenset(ParserCapability(c) for c in data.get("capabilities", []))

    return ParseResult(
        reuse_key=data["reuse_key"],
        language=data["language"],
        fingerprint=fp,
        tree=tree,
        extracted=extracted,
        diagnostics=diagnostics,
        timing=timing,
        capabilities=capabilities,
        from_cache=data.get("from_cache", False),
    )


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


def _serialize_node(node: SyntaxNode) -> Dict[str, Any]:
    return {
        "kind": node.kind,
        "span": _serialize_span(node.span),
        "children": [_serialize_node(c) for c in node.children],
        "field_name": node.field_name,
        "is_named": node.is_named,
        "is_error": node.is_error,
        "is_missing": node.is_missing,
    }


def _deserialize_node(d: Dict[str, Any]) -> SyntaxNode:
    return SyntaxNode(
        kind=d["kind"],
        span=_deserialize_span(d["span"]),
        children=tuple(_deserialize_node(c) for c in d.get("children", [])),
        field_name=d.get("field_name"),
        is_named=d.get("is_named", True),
        is_error=d.get("is_error", False),
        is_missing=d.get("is_missing", False),
    )


def _serialize_tree(tree: SyntaxTree) -> Dict[str, Any]:
    ch_str = (
        tree.content_hash.value
        if hasattr(tree.content_hash, "value")
        else str(tree.content_hash)
    )
    sb_str = (
        tree.source_bytes.decode("latin1")
        if isinstance(tree.source_bytes, bytes)
        else tree.source_bytes
    )
    return {
        "language": tree.language,
        "root": _serialize_node(tree.root),
        "content_hash": ch_str,
        "source_bytes": sb_str,
        "truncated": tree.truncated,
    }


def _deserialize_tree(d: Dict[str, Any]) -> SyntaxTree:
    ch = (
        ContentHash(d["content_hash"])
        if isinstance(d["content_hash"], str)
        else d["content_hash"]
    )
    sb = (
        d["source_bytes"].encode("latin1")
        if isinstance(d["source_bytes"], str)
        else d["source_bytes"]
    )
    return SyntaxTree(
        language=d["language"],
        root=_deserialize_node(d["root"]),
        content_hash=ch,
        source_bytes=sb,
        truncated=d.get("truncated", False),
    )


def _serialize_extracted(ext: ExtractedSyntax) -> Dict[str, Any]:
    return {
        "declarations": [
            {
                "kind": decl.kind.value,
                "name": decl.name,
                "span": _serialize_span(decl.span),
                "name_span": _serialize_span(decl.name_span),
                "node_kind": decl.node_kind,
                "container_path": list(decl.container_path),
                "visibility": decl.visibility.value,
                "annotations": [
                    {
                        "name": a.name,
                        "span": _serialize_span(a.span),
                        "arguments_text": a.arguments_text,
                    }
                    for a in decl.annotations
                ],
                "documentation": (
                    {
                        "text": decl.documentation.text,
                        "span": _serialize_span(decl.documentation.span),
                        "is_leading": decl.documentation.is_leading,
                    }
                    if decl.documentation
                    else None
                ),
                "signature_text": decl.signature_text,
                "modifiers": list(decl.modifiers),
                "is_exported": decl.is_exported,
            }
            for decl in ext.declarations
        ],
        "imports": [
            {
                "module_text": imp.module_text,
                "span": _serialize_span(imp.span),
                "node_kind": imp.node_kind,
                "names": [{"name": n.name, "alias": n.alias} for n in imp.names],
                "is_relative": imp.is_relative,
                "is_type_only": imp.is_type_only,
                "is_side_effect_only": imp.is_side_effect_only,
            }
            for imp in ext.imports
        ],
        "exports": [
            {
                "span": _serialize_span(exp.span),
                "node_kind": exp.node_kind,
                "names": [{"name": n.name, "alias": n.alias} for n in exp.names],
                "module_text": exp.module_text,
                "is_default": exp.is_default,
                "is_wildcard": exp.is_wildcard,
            }
            for exp in ext.exports
        ],
        "comments": [
            {
                "text": c.text,
                "span": _serialize_span(c.span),
                "node_kind": c.node_kind,
                "is_block": c.is_block,
            }
            for c in ext.comments
        ],
    }


def _deserialize_extracted(d: Dict[str, Any]) -> ExtractedSyntax:
    declarations = [
        SyntaxDeclaration(
            kind=DeclarationKind(item["kind"]),
            name=item["name"],
            span=_deserialize_span(item["span"]),
            name_span=_deserialize_span(item["name_span"]),
            node_kind=item["node_kind"],
            container_path=tuple(item.get("container_path", ())),
            visibility=Visibility(item.get("visibility", "not_applicable")),
            annotations=tuple(
                Annotation(
                    name=a["name"],
                    span=_deserialize_span(a["span"]),
                    arguments_text=a.get("arguments_text"),
                )
                for a in item.get("annotations", [])
            ),
            documentation=(
                DocComment(
                    text=item["documentation"]["text"],
                    span=_deserialize_span(item["documentation"]["span"]),
                    is_leading=item["documentation"].get("is_leading", True),
                )
                if item.get("documentation")
                else None
            ),
            signature_text=item.get("signature_text"),
            modifiers=tuple(item.get("modifiers", ())),
            is_exported=item.get("is_exported", False),
        )
        for item in d.get("declarations", [])
    ]

    imports = [
        ImportStatement(
            module_text=item["module_text"],
            span=_deserialize_span(item["span"]),
            node_kind=item["node_kind"],
            names=tuple(
                ImportedName(name=n["name"], alias=n.get("alias"))
                for n in item.get("names", [])
            ),
            is_relative=item.get("is_relative", False),
            is_type_only=item.get("is_type_only", False),
            is_side_effect_only=item.get("is_side_effect_only", False),
        )
        for item in d.get("imports", [])
    ]

    exports = [
        ExportStatement(
            span=_deserialize_span(item["span"]),
            node_kind=item["node_kind"],
            names=tuple(
                ImportedName(name=n["name"], alias=n.get("alias"))
                for n in item.get("names", [])
            ),
            module_text=item.get("module_text"),
            is_default=item.get("is_default", False),
            is_wildcard=item.get("is_wildcard", False),
        )
        for item in d.get("exports", [])
    ]

    comments = [
        CommentBlock(
            text=item["text"],
            span=_deserialize_span(item["span"]),
            node_kind=item["node_kind"],
            is_block=item.get("is_block", False),
        )
        for item in d.get("comments", [])
    ]

    return ExtractedSyntax(
        declarations=tuple(declarations),
        imports=tuple(imports),
        exports=tuple(exports),
        comments=tuple(comments),
    )


def _serialize_diagnostic(diag: ParseDiagnostic) -> Dict[str, Any]:
    return {
        "severity": diag.severity.value,
        "message": diag.message,
        "span": _serialize_span(diag.span) if diag.span is not None else None,
        "node_kind": diag.node_kind,
    }


def _deserialize_diagnostic(d: Dict[str, Any]) -> ParseDiagnostic:
    return ParseDiagnostic(
        severity=DiagnosticSeverity(d["severity"]),
        message=d["message"],
        span=_deserialize_span(d["span"]) if d.get("span") is not None else None,
        node_kind=d.get("node_kind"),
    )
