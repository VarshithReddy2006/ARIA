-- Schema migration for Milestone 8 — AI Context & Retrieval Engine
-- Version: 8

CREATE TABLE IF NOT EXISTS ria_context_plan (
    plan_id TEXT NOT NULL PRIMARY KEY,
    intent_type TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_context_cache (
    cache_key_digest TEXT NOT NULL PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    prompt_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ria_context_cache_commit ON ria_context_cache(commit_sha);
