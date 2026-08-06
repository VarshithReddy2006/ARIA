"""Integration tests for SqliteSemanticCacheStore (Phase 9 & 15)."""

from __future__ import annotations

from ria.domain.identity import ContentHash
from ria.domain.models.parser_identity import ComponentVersion, ParserFingerprint
from ria.domain.models.semantic_identity import SemanticCacheKey, SemanticFingerprint
from ria.domain.models.semantic_result import ResolutionResult
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import MigrationRunner
from ria.infrastructure.storage.sqlite.semantic_cache_store import (
    SqliteSemanticCacheStore,
)


def test_sqlite_semantic_cache_store(tmp_path) -> None:
    db_path = tmp_path / "ria.db"
    connections = ConnectionProvider(db_path)
    MigrationRunner(connections).run()

    cache_store = SqliteSemanticCacheStore(connections)

    parser_fp = ParserFingerprint(
        parser=ComponentVersion("tree-sitter", "0.21.0"),
        extractor=ComponentVersion("py-extractor", "1.0.0"),
        language=ComponentVersion("python", "3.12"),
    )
    sem_fp = SemanticFingerprint(
        resolver_name="python-resolver",
        resolver_version="1.0.0",
        parser_fingerprint=parser_fp,
        language="python",
    )
    ch = ContentHash.of_bytes(b"sample_code")
    key = SemanticCacheKey(content_hash=ch, language="python", fingerprint=sem_fp)

    res = ResolutionResult()
    cache_store.put(key, res)

    cached = cache_store.get(key)
    assert cached is not None
    assert cached.from_cache

    purged = cache_store.invalidate_by_reuse_key(key.reuse_key)
    assert purged == 1
    assert cache_store.get(key) is None

    connections.close()
