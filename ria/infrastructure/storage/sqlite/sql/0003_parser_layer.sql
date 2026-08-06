-- Milestone 3: Parser Layer
--
-- Adds the durable parse cache table of SDD section 3 and section 5.5.
-- Keyed by cache_key_digest (SHA-256 of reuse_key + fingerprint token).
-- Enables content-addressed parse reuse across commits, branches, and repositories.

CREATE TABLE IF NOT EXISTS ria_parse_cache (
    cache_key_digest   TEXT PRIMARY KEY,
    reuse_key          TEXT NOT NULL,
    language           TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    fingerprint_token  TEXT NOT NULL,
    result_json        TEXT NOT NULL,
    cached_at          TEXT NOT NULL
);

-- Fast lookup and invalidation by reuse_key (content_hash|language)
CREATE INDEX IF NOT EXISTS ix_ria_parse_cache_reuse_key
    ON ria_parse_cache (reuse_key);

-- Fast invalidation by fingerprint_digest
CREATE INDEX IF NOT EXISTS ix_ria_parse_cache_fingerprint
    ON ria_parse_cache (fingerprint_digest);
