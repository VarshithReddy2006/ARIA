-- Schema migration for Milestone 9 — AI Reasoning Engine
-- Version: 9

CREATE TABLE IF NOT EXISTS ria_reasoning_request (
    reasoning_id TEXT NOT NULL PRIMARY KEY,
    model_name TEXT NOT NULL,
    request_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_reasoning_cache (
    cache_key_digest TEXT NOT NULL PRIMARY KEY,
    fingerprint_digest TEXT NOT NULL,
    result_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_streaming_session (
    session_id TEXT NOT NULL PRIMARY KEY,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ria_reasoning_cache_fp ON ria_reasoning_cache(fingerprint_digest);
