-- Migration 0004: Semantic Resolution Layer schema

CREATE TABLE IF NOT EXISTS ria_semantic_cache (
    cache_key_digest TEXT PRIMARY KEY,
    reuse_key TEXT NOT NULL,
    language TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    fingerprint_token TEXT NOT NULL,
    result_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ria_semantic_cache_reuse_key ON ria_semantic_cache (reuse_key);
CREATE INDEX IF NOT EXISTS idx_ria_semantic_cache_fp ON ria_semantic_cache (fingerprint_digest);
