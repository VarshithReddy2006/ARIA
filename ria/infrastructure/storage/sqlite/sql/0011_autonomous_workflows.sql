-- Schema migration for Milestone 11 — Autonomous Development Workflow Engine
-- Version: 11

CREATE TABLE IF NOT EXISTS ria_workflow_session (
    workflow_id TEXT NOT NULL PRIMARY KEY,
    definition_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    current_state TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_workflow_approval (
    request_id TEXT NOT NULL PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    approver_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_workflow_audit (
    entry_id TEXT NOT NULL PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_workflow_cache (
    cache_key_digest TEXT NOT NULL PRIMARY KEY,
    result_json TEXT NOT NULL,
    cached_at TEXT NOT NULL
);
