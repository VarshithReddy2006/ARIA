"""SQLite persistence and cache implementations for Milestone 8 AI Context Engine.

Implements :class:`~ria.ports.context.ContextCacheStore`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.errors import StorageError
from ria.domain.identity import CommitSha
from ria.domain.models.context_result import ContextCacheKey
from ria.domain.models.prompt_context import (
    ContextCitation,
    PromptContext,
    PromptMessage,
    PromptSection,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.context import ContextCacheStore

__all__ = ["SqliteContextCacheStore"]


class SqliteContextCacheStore(ContextCacheStore):
    """SQLite implementation of ContextCacheStore."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: ContextCacheKey) -> Optional[PromptContext]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT prompt_json FROM ria_context_cache WHERE cache_key_digest = ?",
                (digest,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _deserialize_prompt_context(json.loads(row[0]))
        except Exception as exc:
            raise StorageError(f"failed to read context cache entry: {exc}") from exc

    def put(self, key: ContextCacheKey, prompt: PromptContext) -> None:
        digest = key.digest()
        sha = key.commit_sha.value
        fp_digest = key.fingerprint.digest()
        prompt_json = json.dumps(_serialize_prompt_context(prompt), default=str)
        cached_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_context_cache (cache_key_digest, commit_sha, fingerprint_digest, prompt_json, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET prompt_json = excluded.prompt_json, cached_at = excluded.cached_at
                """,
                (digest, sha, fp_digest, prompt_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write context cache entry: {exc}") from exc

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "DELETE FROM ria_context_cache WHERE commit_sha = ?",
                (commit_sha.value,),
            )
            return cursor.rowcount
        except Exception as exc:
            raise StorageError(
                f"failed to invalidate context cache by commit: {exc}"
            ) from exc


def _serialize_prompt_context(p: PromptContext) -> Dict[str, Any]:
    return {
        "sections": [
            {"title": s.title, "content": s.content, "token_count": s.token_count}
            for s in p.sections
        ],
        "messages": [{"role": m.role, "content": m.content} for m in p.messages],
        "citations": [
            {
                "repository": c.repository,
                "file_path": c.file_path,
                "symbol_name": c.symbol_name,
                "line_start": c.line_start,
                "line_end": c.line_end,
                "node_id": c.node_id,
                "relationship": c.relationship,
            }
            for c in p.citations
        ],
        "total_tokens": p.total_tokens,
    }


def _deserialize_prompt_context(d: Dict[str, Any]) -> PromptContext:
    sections = tuple(
        PromptSection(
            title=s["title"], content=s["content"], token_count=s.get("token_count", 0)
        )
        for s in d.get("sections", [])
    )
    messages = tuple(
        PromptMessage(role=m["role"], content=m["content"])
        for m in d.get("messages", [])
    )
    citations = tuple(
        ContextCitation(
            repository=c["repository"],
            file_path=c["file_path"],
            symbol_name=c.get("symbol_name"),
            line_start=c.get("line_start"),
            line_end=c.get("line_end"),
            node_id=c.get("node_id"),
            relationship=c.get("relationship"),
        )
        for c in d.get("citations", [])
    )
    return PromptContext(
        sections=sections,
        messages=messages,
        citations=citations,
        total_tokens=d.get("total_tokens", 0),
    )
