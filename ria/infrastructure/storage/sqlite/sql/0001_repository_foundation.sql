-- Milestone 1: Repository Foundation
--
-- Implements the facts store of SDD section 6.2 for the entities of Twin Spec
-- section 3.2 that Milestone 1 covers: Repository, Commit, Branch, FileUnit.
--
-- Conventions
--   * Table names are prefixed `ria_` so this migration chain cannot collide
--     with the legacy application's tables, even if a deployment ever points
--     both at one file.
--   * Timestamps are stored as ISO-8601 strings in UTC with an explicit offset.
--     SQLite has no native datetime type; text is comparable, sortable, and
--     unambiguous, whereas an integer epoch loses the offset and invites the
--     naive/aware confusion the Clock port exists to prevent.
--   * Structured values (index policy, coverage, merge base cache) are stored as
--     JSON text. They are read and written as a whole by one owner, are never
--     filtered on, and their shape evolves additively per Twin Spec section 10.
--     Normalising them would add joins with no query benefit.
--   * Every repository-owned table cascades on repository delete, so the
--     terminal `archived -> purged` lifecycle step is a single statement.

-- ---------------------------------------------------------------------------
-- Repository: the only mutable entity in the structural core.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_repository (
    repository_id     TEXT    PRIMARY KEY,
    moniker           TEXT    NOT NULL UNIQUE,
    origin_url        TEXT    NOT NULL,
    default_branch    TEXT    NOT NULL,
    tenant_id         TEXT    NOT NULL,
    status            TEXT    NOT NULL,
    degraded_reason   TEXT,
    index_policy      TEXT    NOT NULL,
    languages         TEXT    NOT NULL,
    frameworks        TEXT    NOT NULL,
    size_metrics      TEXT    NOT NULL,
    registered_at     TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    last_indexed_at   TEXT,
    last_indexed_sha  TEXT,

    -- Mirrors the domain invariant that a degraded repository must state why
    -- (PRD principle P11). Enforced here as well as in the entity so that a
    -- direct write through another client cannot introduce silent degradation.
    CHECK (
        (status = 'degraded' AND degraded_reason IS NOT NULL)
        OR (status <> 'degraded' AND degraded_reason IS NULL)
    )
);

-- Tenant-scoped listing, ordered by moniker for stable pagination.
CREATE INDEX IF NOT EXISTS ix_ria_repository_tenant_moniker
    ON ria_repository (tenant_id, moniker);

-- Selecting work by lifecycle state, for example every repository to refresh.
CREATE INDEX IF NOT EXISTS ix_ria_repository_status
    ON ria_repository (status, moniker);

-- ---------------------------------------------------------------------------
-- Commit: facts are immutable once queryable.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_commit (
    repository_id     TEXT    NOT NULL,
    sha               TEXT    NOT NULL,
    parents           TEXT    NOT NULL,
    tree_hash         TEXT    NOT NULL,
    author_name       TEXT    NOT NULL,
    author_email      TEXT,
    committer_name    TEXT    NOT NULL,
    committer_email   TEXT,
    authored_at       TEXT    NOT NULL,
    committed_at      TEXT    NOT NULL,
    message           TEXT    NOT NULL,
    files_changed     INTEGER NOT NULL DEFAULT 0,
    insertions        INTEGER NOT NULL DEFAULT 0,
    deletions         INTEGER NOT NULL DEFAULT 0,
    index_state       TEXT    NOT NULL,
    failure_reason    TEXT,
    coverage          TEXT,
    indexed_at        TEXT,

    -- Digest over the immutable fields, per Commit.facts_fingerprint(). The
    -- adapter compares this on every write and refuses a rewrite once the
    -- commit is queryable, which enforces the Twin Spec section 3.2 sentence
    -- "Never updated after reaching queryable".
    facts_fingerprint TEXT    NOT NULL,

    PRIMARY KEY (repository_id, sha),
    FOREIGN KEY (repository_id) REFERENCES ria_repository (repository_id)
        ON DELETE CASCADE,

    CHECK (
        (index_state = 'failed' AND failure_reason IS NOT NULL)
        OR (index_state <> 'failed' AND failure_reason IS NULL)
    )
);

-- Work selection by state, oldest committed first: a later commit's incremental
-- build reuses an earlier commit's parse cache, so history order is the correct
-- processing order.
CREATE INDEX IF NOT EXISTS ix_ria_commit_state_committed
    ON ria_commit (repository_id, index_state, committed_at);

-- Latest queryable commit, which is what an unpinned query resolves to.
CREATE INDEX IF NOT EXISTS ix_ria_commit_committed
    ON ria_commit (repository_id, committed_at DESC);

-- ---------------------------------------------------------------------------
-- Branch: a pointer plus a discardable merge-base cache.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_branch (
    repository_id     TEXT    NOT NULL,
    name              TEXT    NOT NULL,
    head_sha          TEXT    NOT NULL,
    is_default        INTEGER NOT NULL DEFAULT 0,
    is_protected      INTEGER NOT NULL DEFAULT 0,
    last_commit_at    TEXT,
    updated_at        TEXT    NOT NULL,
    merge_base_cache  TEXT    NOT NULL DEFAULT '{}',

    PRIMARY KEY (repository_id, name),
    FOREIGN KEY (repository_id) REFERENCES ria_repository (repository_id)
        ON DELETE CASCADE,

    CHECK (is_default IN (0, 1)),
    CHECK (is_protected IN (0, 1))
);

-- Partial unique index: at most one default branch per repository. A partial
-- index is the right tool because the constraint applies only to the rows where
-- is_default is 1, and a plain unique index would forbid more than one
-- non-default branch.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ria_branch_default
    ON ria_branch (repository_id) WHERE is_default = 1;

-- ---------------------------------------------------------------------------
-- FileUnit: the highest-volume entity at this milestone.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_file_unit (
    repository_id       TEXT    NOT NULL,
    commit_sha          TEXT    NOT NULL,
    path                TEXT    NOT NULL,
    content_hash        TEXT    NOT NULL,
    blob_sha            TEXT    NOT NULL,
    language            TEXT    NOT NULL,
    language_tier       TEXT    NOT NULL,
    size_bytes          INTEGER NOT NULL,
    line_count          INTEGER,
    classification      TEXT    NOT NULL,
    parse_status        TEXT    NOT NULL,
    parse_status_reason TEXT,
    module_moniker      TEXT,

    PRIMARY KEY (repository_id, commit_sha, path),
    FOREIGN KEY (repository_id) REFERENCES ria_repository (repository_id)
        ON DELETE CASCADE
);

-- Content-hash lookup across every commit and branch. This is the index that
-- makes the parse reuse of Twin Spec section 6.4 possible: it answers "has this
-- exact content been seen before, anywhere" without scanning.
CREATE INDEX IF NOT EXISTS ix_ria_file_unit_content_hash
    ON ria_file_unit (content_hash);

-- Coverage aggregation per commit and language, used to compute CommitCoverage
-- without loading file unit entities.
CREATE INDEX IF NOT EXISTS ix_ria_file_unit_commit_language
    ON ria_file_unit (repository_id, commit_sha, language);
