"""SQLite persistence and cache implementations for Milestone 9 AI Reasoning Engine.

Implements :class:`~ria.ports.reasoning.ReasoningCacheStore`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional

from ria.domain.errors import StorageError
from ria.domain.identity import CommitSha
from ria.domain.models.reasoning_result import (
    ReasoningCacheKey,
    ReasoningCitation,
    ReasoningEvidence,
    ReasoningMetadata,
    ReasoningResult,
    ReasoningStatistics,
    ResponseQuality,
    ValidationResult,
)
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.ports.reasoning import ReasoningCacheStore

__all__ = ["SqliteReasoningCacheStore"]


class SqliteReasoningCacheStore(ReasoningCacheStore):
    """SQLite implementation of ReasoningCacheStore."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get(self, key: ReasoningCacheKey) -> Optional[ReasoningResult]:
        digest = key.digest()
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT result_json FROM ria_reasoning_cache WHERE cache_key_digest = ?",
                (digest,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _deserialize_reasoning_result(json.loads(row[0]))
        except Exception as exc:
            raise StorageError(f"failed to read reasoning cache entry: {exc}") from exc

    def put(self, key: ReasoningCacheKey, result: ReasoningResult) -> None:
        digest = key.digest()
        fp_digest = key.fingerprint.digest()
        result_json = json.dumps(_serialize_reasoning_result(result), default=str)
        cached_at = datetime.now(timezone.utc).isoformat()

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_reasoning_cache (cache_key_digest, fingerprint_digest, result_json, cached_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key_digest) DO UPDATE SET result_json = excluded.result_json, cached_at = excluded.cached_at
                """,
                (digest, fp_digest, result_json, cached_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write reasoning cache entry: {exc}") from exc

    def invalidate_by_commit(self, commit_sha: CommitSha) -> int:
        return 0


def _serialize_reasoning_result(r: ReasoningResult) -> Dict[str, Any]:
    return {
        "answer": r.answer,
        "evidence": [
            {"id": e.evidence_id, "file": e.source_file, "snippet": e.content_snippet}
            for e in r.evidence
        ],
        "citations": [
            {"file": c.file_path, "symbol": c.symbol_name} for c in r.citations
        ],
        "validation": {"is_valid": r.validation.is_valid},
        "quality": {"groundedness": r.quality.groundedness_score},
        "statistics": {"latency": r.statistics.latency_seconds, "cache_hit": True},
        "metadata": {
            "id": r.metadata.reasoning_id,
            "provider": r.metadata.provider_name,
            "model": r.metadata.model_name,
        },
    }


def _deserialize_reasoning_result(d: Dict[str, Any]) -> ReasoningResult:
    answer = d.get("answer", "")
    evidence = tuple(
        ReasoningEvidence(
            evidence_id=e["id"], source_file=e["file"], content_snippet=e["snippet"]
        )
        for e in d.get("evidence", [])
    )
    citations = tuple(
        ReasoningCitation(file_path=c["file"], symbol_name=c.get("symbol"))
        for c in d.get("citations", [])
    )
    validation = ValidationResult(
        is_valid=d.get("validation", {}).get("is_valid", True)
    )
    quality = ResponseQuality(
        groundedness_score=d.get("quality", {}).get("groundedness", 1.0)
    )
    stats = ReasoningStatistics(
        latency_seconds=d.get("statistics", {}).get("latency", 0.0), cache_hit=True
    )
    meta_d = d.get("metadata", {})
    metadata = ReasoningMetadata(
        reasoning_id=meta_d.get("id", "cached"),
        provider_name=meta_d.get("provider", "local"),
        model_name=meta_d.get("model", "mock"),
    )

    return ReasoningResult(
        answer=answer,
        evidence=evidence,
        citations=citations,
        validation=validation,
        quality=quality,
        statistics=stats,
        metadata=metadata,
    )
