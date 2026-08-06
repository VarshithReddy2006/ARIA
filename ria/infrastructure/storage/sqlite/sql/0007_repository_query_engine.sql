-- Schema migration for Milestone 7 — Repository Query & Analysis Engine
-- Version: 7

CREATE TABLE IF NOT EXISTS ria_saved_query (
    query_id TEXT NOT NULL PRIMARY KEY,
    query_type TEXT NOT NULL,
    request_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_query_cache (
    cache_key_digest TEXT NOT NULL PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    result_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_analysis_result (
    analysis_id TEXT NOT NULL PRIMARY KEY,
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ria_query_cache_commit ON ria_query_cache(commit_sha);
CREATE INDEX IF NOT EXISTS idx_ria_analysis_repo ON ria_analysis_result(repository_id, commit_sha);
