"""Integration tests for SqliteParseCacheStore."""

from __future__ import annotations

from datetime import datetime, timezone

from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import (
    ComponentVersion,
    ParseCacheKey,
    ParserFingerprint,
)
from ria.domain.models.span import SourcePosition, SourceSpan
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.parse_cache_store import SqliteParseCacheStore

CONTENT_HASH = "sha256:" + "a" * 64
REUSE_KEY = f"{CONTENT_HASH}|python"


def span(start: int = 0, end: int = 10) -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(byte=start, line=0, column=start),
        end=SourcePosition(byte=end, line=0, column=end),
    )


def make_fingerprint(ver: str = "1.0.0") -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter-python", "0.21.0"),
        extractor=ComponentVersion("python-extractor", ver),
        language=ComponentVersion("python-plugin", "1.0.0"),
    )


def make_tree(language: str = "python") -> SyntaxTree:
    return SyntaxTree(
        language=language,
        root=SyntaxNode(kind="module", span=span(0, 10)),
        content_hash=CONTENT_HASH,
        source_bytes=10,
    )


class TestSqliteParseCacheStore:
    def test_put_get_clear(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        connections = ConnectionProvider(db_path)
        MigrationRunner(connections).run()

        store = SqliteParseCacheStore(connections)
        fp = make_fingerprint("1.0.0")
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fp)
        res = ParseResult(
            reuse_key=REUSE_KEY,
            language="python",
            fingerprint=fp,
            tree=make_tree("python"),
        )
        now = datetime.now(timezone.utc)
        entry = ParseCacheEntry(key=key, result=res, cached_at=now)

        # 1. Get absent entry -> None
        assert store.get(key) is None

        # 2. Put entry
        store.put(entry)

        # 3. Get entry -> returned and matches
        loaded = store.get(key)
        assert loaded is not None
        assert loaded.key == key
        assert loaded.result.reuse_key == REUSE_KEY
        assert loaded.result.language == "python"
        assert loaded.result.tree is not None
        assert loaded.result.tree.root.kind == "module"

        # 4. Invalidate by reuse_key
        count = store.invalidate_by_reuse_key(REUSE_KEY)
        assert count == 1
        assert store.get(key) is None

        # 5. Put again and clear
        store.put(entry)
        store.clear()
        assert store.get(key) is None
