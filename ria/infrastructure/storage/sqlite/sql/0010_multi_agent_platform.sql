-- Schema migration for Milestone 10 — Multi-Agent Developer Platform
-- Version: 10

CREATE TABLE IF NOT EXISTS ria_agent_session (
    session_id TEXT NOT NULL PRIMARY KEY,
    repository_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_agent_task_assignment (
    task_id TEXT NOT NULL PRIMARY KEY,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    task_json TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_agent_report (
    session_id TEXT NOT NULL PRIMARY KEY,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ria_agent_conversation (
    conversation_id TEXT NOT NULL PRIMARY KEY,
    session_id TEXT NOT NULL,
    messages_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
