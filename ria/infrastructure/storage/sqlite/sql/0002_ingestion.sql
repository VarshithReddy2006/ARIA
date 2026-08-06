-- Milestone 2: Repository Ingestion
--
-- Adds the durable job queue of SDD section 4. No other table is required:
-- Milestone 1's `ria_file_unit` already stores each commit's tree, so change
-- detection compares two queries against it rather than a separate manifest
-- table. A dedicated manifest table would duplicate that data and give two
-- sources of truth for one fact.
--
-- Conventions follow migration 0001: `ria_` prefix, ISO-8601 UTC timestamps as
-- text, JSON text for structured values read and written whole by one owner.

-- ---------------------------------------------------------------------------
-- Job: durable, lease-based work queue.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_job (
    job_id          TEXT    PRIMARY KEY,
    repository_id   TEXT    NOT NULL,
    kind            TEXT    NOT NULL,
    idempotency_key TEXT    NOT NULL,
    payload         TEXT    NOT NULL DEFAULT '{}',
    state           TEXT    NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0,
    attempts        INTEGER NOT NULL DEFAULT 0,
    retry_policy    TEXT    NOT NULL,
    available_at    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    leased_until    TEXT,
    lease_owner     TEXT,
    stage           TEXT,
    last_error      TEXT,

    FOREIGN KEY (repository_id) REFERENCES ria_repository (repository_id)
        ON DELETE CASCADE,

    -- Mirrors the entity invariant that a leased job records both its deadline
    -- and its owner. Enforced here as well so that a lease written directly
    -- through another SQLite client cannot become unreclaimable: a lease with no
    -- deadline would never expire and its job would stall the queue forever.
    CHECK (
        (state = 'leased' AND leased_until IS NOT NULL AND lease_owner IS NOT NULL)
        OR (state <> 'leased' AND leased_until IS NULL AND lease_owner IS NULL)
    ),

    -- A dead job must say why. Without a reason an operator has nothing to act
    -- on, and PRD principle P11 forbids failure that does not state its cause.
    CHECK (state <> 'dead' OR last_error IS NOT NULL),

    CHECK (attempts >= 0),
    CHECK (priority BETWEEN -100 AND 100)
);

-- Idempotency, enforced by the database rather than by a read-then-write in the
-- adapter. A unique constraint is atomic under concurrency; a check-then-insert
-- would let two workers enqueue the same key simultaneously, which is exactly the
-- duplicate-work case the key exists to prevent.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ria_job_idempotency
    ON ria_job (repository_id, idempotency_key);

-- The claim query: the most urgent available job of a permitted kind. Column
-- order matches the ORDER BY of `lease_next` so the index serves both the filter
-- and the sort, which keeps claiming a seek rather than a scan as the queue grows.
CREATE INDEX IF NOT EXISTS ix_ria_job_claim
    ON ria_job (state, priority, available_at, created_at);

-- The expiry sweep: leased jobs ordered by deadline. Partial, because only leased
-- rows can expire and indexing the rest would grow the index without ever being
-- read by this query.
CREATE INDEX IF NOT EXISTS ix_ria_job_lease_expiry
    ON ria_job (leased_until) WHERE state = 'leased';

-- Queue depth per repository, for status reporting and autoscaling signals.
CREATE INDEX IF NOT EXISTS ix_ria_job_repository_state
    ON ria_job (repository_id, state);
