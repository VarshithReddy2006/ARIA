"""In-Process Bounded LRU Cache for ChromaDB Retrieval Queries.

Provides thread-safe, bounded, version-isolated caching of retrieved code chunks
to eliminate repeated ChromaDB disk queries and vector distance re-computations.

Key invariants:
  1. Strict version isolation: every cache key includes the repository's active
     index_version. Any index update automatically makes previous keys invalid.
  2. Thread safety: all reads, writes, and evictions are synchronized via an RLock.
  3. Bounded memory: strict LRU eviction occurs when entry count exceeds max_entries.
  4. Immutability guarantee: results are deep-copied on get/put to prevent downstream mutation.
  5. Explicit invalidation hooks: supports per-repository and global invalidation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_retrieval_query(query: str) -> str:
    """Normalize user retrieval query by stripping markdown formatting, backticks, excess whitespace, and trailing punctuation."""
    if not query or not isinstance(query, str):
        return ""
    q = query.strip()
    # Strip enclosing backticks / markdown formatting
    q = re.sub(r"[`*_~]", "", q)
    # Collapse multiple whitespace characters
    q = re.sub(r"\s+", " ", q).strip()
    # Strip trailing punctuation noise while preserving syntax like () or []
    q = re.sub(r"[?!.,;]+$", "", q).strip()
    return q.lower()


class RetrievalLRUCache:
    """Bounded, thread-safe LRU cache with version isolation for retrieval results."""

    def __init__(
        self,
        max_entries: int = 512,
        ttl_seconds: Optional[float] = 300.0,
    ) -> None:
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._repo_to_keys: Dict[str, set[str]] = {}

        # Telemetry metrics
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0
        self._invalidations: int = 0

    @staticmethod
    def build_key(
        repo_name: str,
        index_version: Optional[str],
        question: str,
        top_k_initial: int = 15,
        top_k_final: int = 5,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Deterministic cache key incorporating all parameters that affect retrieval."""
        norm_repo = (
            repo_name.strip().lower()
            if isinstance(repo_name, str)
            else (str(repo_name).strip().lower() if repo_name is not None else "")
        )
        norm_version = (
            index_version.strip() if isinstance(index_version, str) else "none"
        )
        norm_question = normalize_retrieval_query(question)

        key_payload = {
            "r": norm_repo,
            "v": norm_version,
            "q": norm_question,
            "ki": int(top_k_initial) if isinstance(top_k_initial, (int, float)) else 15,
            "kf": int(top_k_final) if isinstance(top_k_final, (int, float)) else 5,
        }
        if extra and isinstance(extra, dict):
            key_payload["x"] = sorted((str(k), str(v)) for k, v in extra.items())

        payload_bytes = json.dumps(key_payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload_bytes).hexdigest()

    def get(self, key: str) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
        """Retrieve cached (chunks, metrics) if present and not expired."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]
            now = time.time()

            # Check TTL expiry if configured
            if (
                self.ttl_seconds is not None
                and (now - entry["created_at"]) > self.ttl_seconds
            ):
                self._remove_key_unlocked(key)
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1

            # Deep copy to prevent mutation of cached data by caller
            cached_chunks = copy.deepcopy(entry["chunks"])
            cached_metrics = copy.deepcopy(entry["metrics"])
            return cached_chunks, cached_metrics

    def put(
        self,
        key: str,
        repo_name: str,
        chunks: List[Dict[str, Any]],
        metrics: Dict[str, Any],
    ) -> None:
        """Store (chunks, metrics) in LRU cache with eviction if capacity exceeded."""
        with self._lock:
            now = time.time()
            clean_repo = (repo_name or "").strip().lower()

            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = {
                    "chunks": copy.deepcopy(chunks),
                    "metrics": copy.deepcopy(metrics),
                    "repo_name": clean_repo,
                    "created_at": now,
                }
                return

            # Perform LRU eviction if full
            while len(self._cache) >= self.max_entries:
                oldest_key, _ = self._cache.popitem(last=False)
                self._evictions += 1
                # Clean up reverse index
                for k_set in self._repo_to_keys.values():
                    k_set.discard(oldest_key)

            self._cache[key] = {
                "chunks": copy.deepcopy(chunks),
                "metrics": copy.deepcopy(metrics),
                "repo_name": clean_repo,
                "created_at": now,
            }
            if clean_repo not in self._repo_to_keys:
                self._repo_to_keys[clean_repo] = set()
            self._repo_to_keys[clean_repo].add(key)

    def _remove_key_unlocked(self, key: str) -> None:
        """Helper to remove a key and clean reverse lookup without re-locking."""
        if key in self._cache:
            entry = self._cache.pop(key)
            r = entry.get("repo_name", "")
            if r in self._repo_to_keys:
                self._repo_to_keys[r].discard(key)

    def invalidate_repo(self, repo_name: str) -> int:
        """Invalidate all cached entries for a specific repository."""
        with self._lock:
            clean_repo = (repo_name or "").strip().lower()
            keys_to_remove = list(self._repo_to_keys.get(clean_repo, []))
            count = 0
            for k in keys_to_remove:
                if k in self._cache:
                    self._cache.pop(k, None)
                    count += 1
            self._repo_to_keys.pop(clean_repo, None)
            self._invalidations += count
            if count > 0:
                logger.info(
                    "Invalidated %d retrieval cache entries for repo: %s",
                    count,
                    clean_repo,
                )
            return count

    def invalidate_all(self) -> int:
        """Clear all entries across all repositories."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._repo_to_keys.clear()
            self._invalidations += count
            if count > 0:
                logger.info("Cleared entire retrieval cache (%d entries)", count)
            return count

    def clear(self) -> int:
        """Convenience alias for invalidate_all."""
        return self.invalidate_all()

    def get_metrics(self) -> Dict[str, Any]:
        """Return cache health and hit-rate telemetry."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate_pct = (
                round((self._hits / total_requests) * 100.0, 2)
                if total_requests > 0
                else 0.0
            )
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total_requests,
                "hit_rate_pct": hit_rate_pct,
                "current_size": len(self._cache),
                "max_entries": self.max_entries,
                "evictions": self._evictions,
                "invalidations": self._invalidations,
            }

    def reset_metrics(self) -> None:
        """Reset telemetry counters without clearing cache entries."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._invalidations = 0


# Global singleton instance for retrieval caching across the worker process
retrieval_cache = RetrievalLRUCache(max_entries=512, ttl_seconds=300.0)
