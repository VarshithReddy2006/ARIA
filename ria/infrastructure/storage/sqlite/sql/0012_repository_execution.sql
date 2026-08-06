-- Schema migration for Milestone 12 — Repository Execution & Continuous Learning Engine
-- Version: 12

CREATE TABLE IF NOT EXISTS ria_execution_history (
    execution_id TEXT NOT NULL PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_execution_patch (
    patch_id TEXT NOT NULL PRIMARY KEY,
    execution_id TEXT NOT NULL,
    files_changed INTEGER NOT NULL,
    insertions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    patch_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_learning_record (
    record_id TEXT NOT NULL PRIMARY KEY,
    execution_id TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_execution_cache (
    cache_key_digest TEXT NOT NULL PRIMARY KEY,
    patch_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);
