-- Schema migration for Milestone 6 — Repository Digital Twin
-- Version: 6

CREATE TABLE IF NOT EXISTS ria_twin_state (
    repository_id TEXT NOT NULL PRIMARY KEY,
    current_commit_sha TEXT NOT NULL,
    current_branch TEXT,
    status TEXT NOT NULL,
    twin_state TEXT NOT NULL,
    loaded_components_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_twin_snapshot (
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    twin_id TEXT NOT NULL,
    twin_json TEXT NOT NULL,
    fingerprint_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS ria_twin_metrics (
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS ria_twin_cache (
    cache_key_digest TEXT NOT NULL PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ria_twin_snapshot_repo ON ria_twin_snapshot(repository_id);
CREATE INDEX IF NOT EXISTS idx_ria_twin_cache_commit ON ria_twin_cache(commit_sha);
