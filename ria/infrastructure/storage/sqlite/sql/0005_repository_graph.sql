-- Migration 0005: Repository Knowledge Graph schema

CREATE TABLE IF NOT EXISTS ria_graph_snapshot (
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    statistics_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS ria_graph_node (
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    node_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT,
    location_path TEXT,
    symbol_id TEXT,
    scope_id TEXT,
    node_json TEXT NOT NULL,
    PRIMARY KEY (repository_id, commit_sha, node_id)
);

CREATE INDEX IF NOT EXISTS idx_ria_graph_node_sym ON ria_graph_node (repository_id, commit_sha, symbol_id);
CREATE INDEX IF NOT EXISTS idx_ria_graph_node_path ON ria_graph_node (repository_id, commit_sha, location_path);
CREATE INDEX IF NOT EXISTS idx_ria_graph_node_kind ON ria_graph_node (repository_id, commit_sha, kind);

CREATE TABLE IF NOT EXISTS ria_graph_edge (
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    edge_json TEXT NOT NULL,
    PRIMARY KEY (repository_id, commit_sha, edge_id)
);

CREATE INDEX IF NOT EXISTS idx_ria_graph_edge_src ON ria_graph_edge (repository_id, commit_sha, source_id);
CREATE INDEX IF NOT EXISTS idx_ria_graph_edge_tgt ON ria_graph_edge (repository_id, commit_sha, target_id);
CREATE INDEX IF NOT EXISTS idx_ria_graph_edge_kind ON ria_graph_edge (repository_id, commit_sha, kind);

CREATE TABLE IF NOT EXISTS ria_graph_cache (
    cache_key_digest TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ria_graph_cache_commit ON ria_graph_cache (commit_sha);
