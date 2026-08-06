# Milestone 1 — Repository Foundation

**Status:** complete
**Implements:** SDD section 3 (L1 Ingestion foundations), the cross-cutting Storage,
Configuration and Observability concerns of SDD section 2.1, and the ``Repository``,
``Commit``, ``Branch``, ``FileUnit`` and ``CommitManifest`` entities of Twin Spec
section 3.2.
**Package:** `ria/`
**Tests:** 658 measured (471 unit, 187 integration)

---

## 1. Scope

Delivered exactly the Milestone 1 list and nothing beyond it.

| Item | Where |
|---|---|
| Repository Manager | `ria/application/repository_manager.py` |
| Git Repository Service | `ria/infrastructure/git/subprocess_git_client.py` |
| Repository Registration | `RepositoryManager.register` |
| Repository Configuration | `IndexPolicy`, `RetentionPolicy`, `AdmissionLimits` |
| Repository Metadata | `LanguageProfile`, `SizeMetrics`, `RepositoryManager.update_metadata` |
| Commit Resolution | `ria/application/commit_resolver.py` |
| Content Addressable Storage | `ria/infrastructure/storage/filesystem_blob_store.py` |
| File Unit Model | `ria/domain/models/file_unit.py` |
| Repository Identity | `ria/domain/identity.py` |
| Domain Models | `ria/domain/models/` |
| Persistence Models | `ria/infrastructure/storage/sqlite/sql/0001_repository_foundation.sql` |
| Repository Interfaces | `ria/ports/` |
| Dependency Injection | `ria/container.py` |
| Configuration | `ria/config/settings.py` |
| Logging | `ria/observability/logging.py` |
| Testing | `tests/ria/` |

**Deliberately excluded**, because the milestone plan assigns them to Milestone 2:
clone and fetch, file enumeration, change detection, the diff engine, ingestion
workers, the job queue, and progress tracking. Where an interface was needed to
express a Milestone 1 concept, the interface exists and its implementation does
not — no placeholder, no `NotImplementedError`, enforced by
`tests/ria/integration/test_architecture_rules.py`.

---

## 2. Subsystems

Each subsystem is documented with the six headings the build brief requires.

### 2.1 Domain Model — `ria/domain/`

**Purpose.** Hold the entity model of Twin Spec section 3.2 and the invariants it
declares, so that an invalid entity cannot be represented anywhere in the system.

**Responsibilities.** Identity value objects and their grammars; lifecycle
transition tables; path normalisation; the language and classification catalogue;
entities with construction-time validation and functional transformation.

**Dependencies.** The Python standard library only. Enforced by
`TestDomainPurity`, which fails the build if a domain module imports any `ria`
package other than `ria.domain`, or any third-party distribution.

**Data flow.** Inbound only. Every layer constructs and reads domain objects; the
domain calls nothing.

**Failure modes.** All are construction-time and non-retryable: an invalid moniker,
content hash, commit SHA or path; an illegal lifecycle transition; a violated
consistency rule such as a degraded repository without a stated reason. Each raises
a `DomainError` subclass carrying structured context.

**Extension points.** New entity kinds are additive enum members; new relations are
additive rows rather than schema changes; new languages are catalogue entries; new
lifecycles are a transition table plus a validator call.

### 2.2 Ports — `ria/ports/`

**Purpose.** Declare every outbound dependency as an interface, so adapters are
substitutable and every layer above is testable without infrastructure.

**Responsibilities.** Six ports: `Clock`, `MetricsSink`, `GitClient`,
`ContentAddressableStore`, the four Repository-pattern stores, and `UnitOfWork`.

**Dependencies.** `ria.domain` only. No third-party imports, so no vendor type
appears in an interface signature.

**Data flow.** Ports define the boundary. Application code depends on them;
infrastructure implements them. `GitClient` returns raw data transfer objects rather
than entities, because git cannot know a `RepositoryId` and an adapter that invented
one would hold domain knowledge.

**Failure modes.** Documented per method as part of the contract, so an adapter
author knows which exception to raise and a caller knows which to expect.

**Extension points.** `typing.Protocol` gives structural typing: an adapter
satisfies a port by shape, so a test double needs no base class and a third-party
object can satisfy a port without a wrapper.

### 2.3 Repository Manager — `ria/application/repository_manager.py`

**Purpose.** Register repositories, hold their configuration, and drive their
lifecycle.

**Responsibilities.** Parse an origin URL into a moniker and a credential-free
origin; register; read; reconfigure; record observed metadata; transition state;
archive; purge.

**Dependencies.** `UnitOfWorkFactory`, `Clock`, `MetricsSink`. No adapter, no
transport, no network.

**Data flow.** `RegisterRepositoryCommand` → moniker derivation → uniqueness check
and insert inside one transaction → `Repository`. Every mutation is
read-modify-write inside a single `BEGIN IMMEDIATE` transaction, so two concurrent
updates cannot each apply to a stale copy.

**Failure modes.** `ApplicationError` for an unparseable origin;
`RepositoryAlreadyExistsError` for a duplicate moniker;
`RepositoryNotFoundError` for an absent record; `IllegalStateTransitionError` for a
disallowed transition; `ApplicationError` when a purge is attempted before
archival. All leave state unchanged.

**Extension points.** Command objects rather than long parameter lists, so a new
input in a later milestone does not change every call site.

Two decisions worth restating. Registration performs **no network access**: it
records intent to index, so a registration cannot fail because a remote is briefly
unreachable. And registration is **not idempotent** — a duplicate raises rather than
returning the existing record, because silently returning it would hide a conflict
in which two callers believe they own the same repository with different policies.

### 2.4 Commit Resolver — `ria/application/commit_resolver.py`

**Purpose.** Turn a ref expression into a commit and record that commit's immutable
facts. This is the first step of every operation in the system, because Twin Spec
section 3.1 Rule 2 requires every fact to be commit-keyed.

**Responsibilities.** Resolve a ref; record commit facts idempotently; read recorded
commits; select pending work in history order; observe and record the branch set.

**Dependencies.** `GitClient`, `UnitOfWorkFactory`, `Clock`, `MetricsSink`.

**Data flow.** ref → `GitClient.resolve_ref` → full object name →
`GitClient.read_commit` → `RawCommit` → mapped to `Commit` in the application layer
→ persisted at `DISCOVERED`.

**Failure modes.** `ValueError` for an empty ref; `RefNotFoundError` for an
unresolvable one; `RepositoryNotFoundError` if the owning repository is unregistered,
which prevents an unreachable orphan fact; `ImmutableFactViolationError` if
re-observed facts differ from those recorded for a queryable commit.

**Extension points.** Branch recording replaces the whole set rather than merging,
which is the only way upstream deletion can be detected, and is the shape Milestone
2's discovery will reuse.

### 2.5 Git Repository Service — `ria/infrastructure/git/subprocess_git_client.py`

**Purpose.** Read-only access to a local git directory. Git is the system of record;
this adapter never writes to it.

**Responsibilities.** Version reporting; ref resolution with commit peeling; commit
metadata; branch enumeration with default detection; recursive tree listing; blob
reading; line counting with git's own binary heuristic.

**Dependencies.** The git executable, `GitSettings`, `MetricsSink`.

**Data flow.** Arguments as a list, never through a shell → subprocess with a
timeout → parsed into raw DTOs.

**Failure modes.** `GitUnavailableError` if the executable is absent;
`GitCommandError` on non-zero exit or timeout, with stderr truncated;
`RefNotFoundError` for a missing ref, commit or tree. A malformed record inside a
listing is logged and skipped rather than aborting the listing, per the L1 rule that
one bad file must not fail a build.

**Extension points.** Stateless with respect to repositories, so one instance serves
every repository in the process. A different VCS is a new adapter behind the same
port.

Three parsing decisions carry the correctness of this adapter. Commit metadata uses
ASCII unit and record separators, because a newline-delimited format truncates every
commit with a body. Tree listing uses `-z`, because a path may legally contain a
newline and a line-oriented parse would split it into two entries. Ref resolution
peels to `^{commit}`, because an annotated tag otherwise resolves to the tag object
and every downstream query fails confusingly. Each is covered by a test that fails
without it.

### 2.6 Content Addressable Storage — `ria/infrastructure/storage/filesystem_blob_store.py`

**Purpose.** Store file content keyed by its own digest.

**Responsibilities.** Idempotent write, in-memory and streaming; read, whole and
streamed; presence checks, single and bulk; metadata; deletion for retention.

**Dependencies.** The filesystem, `MetricsSink`.

**Data flow.** bytes → digest → sharded path → atomic write. Sharding bounds
directory fan-out, which matters because a large monorepo contributes hundreds of
thousands of distinct blobs.

**Failure modes.** `BlobNotFoundError` for an absent key; `StorageError` if content
cannot be written durably.

**Extension points.** Shard geometry is configuration. An object-store adapter behind
the same port is a Phase 6 substitution.

The reason this subsystem exists in Milestone 1 rather than later: Twin Spec section
6.4 states that structural sharing reduces per-commit storage roughly
six-hundredfold and that "without this, commit-addressing is economically
impossible". Content addressing is what makes that sharing automatic rather than
something a caller must arrange — a file unchanged across five hundred commits is
stored once because its digest is unchanged, with no reference counting and no
coordination.

### 2.7 Persistence — `ria/infrastructure/storage/sqlite/`

**Purpose.** Durably store the facts of Milestone 1 with the transactional
guarantees the specification requires.

**Responsibilities.** Connection management with the pragmas SQLite needs under a
worker pool; forward-only checksummed migrations; four store adapters; the unit of
work; domain-to-row mapping in one module.

**Dependencies.** `sqlite3`, the domain, the ports.

**Data flow.** Entity → `mappers` → parameterised SQL → row → `mappers` → entity.
Structured values (index policy, coverage, merge base cache) are stored as JSON
because they are read and written whole by one owner, are never filtered on, and
evolve additively.

**Failure modes.** `StorageError` for connection, transaction and write failures;
`RepositoryAlreadyExistsError` and `RepositoryNotFoundError` translated from
integrity outcomes; `CommitNotFoundError`; `ImmutableFactViolationError` when a
frozen commit's facts would change. Rollback is the default on scope exit, so an
exception, an early return and a forgotten commit all abandon the work rather than
half-applying it.

**Extension points.** All access is behind the ports, which is what keeps the storage
question of SDD open question T2 a substitution rather than a rewrite. `mappers.py`
is the single blast site for that change.

Two enforcement mechanisms are worth naming. `BEGIN IMMEDIATE` acquires the write
lock up front, converting a late busy failure after a worker has done all its work
into a bounded wait. And the `facts_fingerprint` column turns the Twin Spec sentence
"never updated after reaching queryable" into an enforced invariant: the adapter
compares the digest on every write and refuses a mismatch. Enforcing it in the
adapter rather than only in the entity matters because the entity cannot know what
was previously stored, so any code path constructing a fresh entity from re-observed
git data would bypass an in-memory check.

### 2.8 Configuration — `ria/config/settings.py`

**Purpose.** Resolve typed configuration once, at the composition root.

**Responsibilities.** Environment binding under the `RIA_` prefix; path derivation
and absolute resolution; directory creation; a test-confined factory.

**Dependencies.** `pydantic-settings`. This is the only module in `ria` permitted to
import it, enforced by `TestValidationLibraryContainment`.

**Data flow.** Environment → validated settings → passed down as an argument.
Nothing in the system reads an environment variable at the point of use.

**Failure modes.** Pydantic validation errors at construction;
`ConfigurationError` if a required directory cannot be created.

**Extension points.** Nested settings groups per concern, so a new subsystem adds a
group rather than widening one object.

### 2.9 Observability — `ria/observability/`

**Purpose.** Structured logging and metrics available to every layer without any
layer importing a backend.

**Responsibilities.** Context-bound structured logging with human and JSON
formatters; two complete metrics sinks.

**Dependencies.** The standard library only.

**Data flow.** Ambient log context is bound per operation via `log_context` and
merged into every record emitted inside it. Metrics are emitted through the
`MetricsSink` port.

**Failure modes.** None propagate. A sink never raises and never blocks, because a
metrics fault must not fail an index build.

**Extension points.** A Prometheus adapter is deliberately absent: exposition is a
delivery concern and belongs with the HTTP surface. Adding it here would make this
package depend on a web framework's registry.

### 2.10 Composition Root — `ria/container.py`

**Purpose.** The single place where adapters are chosen and wired to ports.

**Responsibilities.** Resolve settings; configure logging; select the metrics sink;
construct the connection provider and run migrations; build the unit-of-work
factory, blob store and git client; construct the use cases; derive mirror paths.

**Dependencies.** Everything. Nothing depends on it, enforced by
`test_nothing_imports_the_composition_root`.

**Data flow.** `build_container(settings)` → immutable `Container`.

**Failure modes.** `ConfigurationError` for an uncreatable directory;
`StorageError` if the database cannot be opened or migrated.

**Extension points.** A function returning a frozen container rather than
module-level singletons. Import has no side effects, two containers coexist in one
process, and a test builds one over a temporary directory in a single line. This is
a direct correction of the prior architecture's import-time mutable singletons,
which SDD section 7 records as having made multi-worker deployment incorrect.

---

## 3. Specification Deviations

Two additions to enumerations, both completing a documented lifecycle rather than
changing a decision. Neither is a redesign; both are recorded here so a reviewer can
reject them.

| Addition | Reason |
|---|---|
| `RepositoryStatus.REGISTERED` | Twin Spec section 3.2 states the lifecycle as beginning at `registered` while its field enumeration omits that state. Without the member, a repository between registration and its first index build is unrepresentable. |
| `ParseStatus.PENDING` | A `FileUnit` is created during ingestion (Milestone 1) before any parser exists (Milestone 3). Without the member, an unparsed file would have to be recorded as `skipped`, which is a false statement about coverage and violates PRD principle P11. |

Also worth recording: `RepositoryStatus.INDEXING` generalises the specification's
`first_index`, because every subsequent build occupies the same state, and a state
that applied only to the first build would leave later builds unrepresentable.

---

## 4. Defects Found and Fixed During Implementation

Three defects were found by tests written against the specification rather than
against the code. Each was fixed in the implementation.

| Defect | Consequence if shipped | Fix |
|---|---|---|
| `parse_origin_url` matched `ftp://host/owner/name` as an scp-style remote | Moniker `repo:ftp:owner/name` — a bogus host that collides across forges, and silent acceptance of an unsupported scheme | The scp branch now also requires that the path not begin with a slash |
| `CommitResolver.resolve` passed the raw ref to git while comparing symbolic status against a stripped copy | An unusable expression sent to git, and a symbolic flag computed against a different string than the one resolved | Normalise once, before the git call; reject an empty expression |
| Test fixtures wrote file content through `write_text` | Platform newline translation produced `\r\n` on Windows. Under content addressing a translated byte is a different file, so fixtures would have described content that was never written | Fixtures write bytes explicitly |

One test was also corrected rather than the code: `ContentAddressableStore.missing`
deduplicates its result, which is the more defensible contract because the caller's
intent is a work list. The port documentation now states it.

---

## 5. Verification

```bash
# Full Milestone 1 suite
pytest tests/ria -q                     # 658 passed

# Layers independently
pytest tests/ria/unit -q                # 471 in 0.8s — no filesystem, database or subprocess
pytest tests/ria/integration -q         # 187 — real adapters

# Architectural rules, executable
pytest tests/ria/integration/test_architecture_rules.py -q

# Lint and format, as CI enforces them
ruff check .
ruff format --check .

# Whole repository, confirming no regression in the legacy suite
pytest -q                               # 1530 passed
```

Environments without a git executable skip the git-dependent tests cleanly via
`tests.ria.conftest.requires_git`; every other test still runs.

### What the architecture tests enforce

`tests/ria/integration/test_architecture_rules.py` is the executable form of SDD
section 2.3, which states the dependency rule is "enforced in CI by static import
analysis". It asserts that no module in `ria` imports the legacy application; that
the domain imports only itself and no third-party distribution; that ports import
only the domain and other ports; that the application never imports infrastructure
and vice versa; that nothing imports the composition root; that pydantic appears in
exactly one module; that no language-model client is imported anywhere; and that no
`NotImplementedError`, unfinished-work marker or empty module exists.

These are the highest-leverage tests in the suite, because they guard a property that
degrades silently. One convenient import from a domain module into an adapter costs
nothing today and makes the layer untestable a year from now. The prior
architecture's `services` package importing `backend.dependencies` is exactly that
outcome, arrived at one import at a time.

---

## 6. Deferred, With Its Consumer Named

Nothing in Milestone 1 is a stub. Two items are deliberately unconsumed until a
later milestone, and are recorded here so that neither becomes a silent dead
setting of the kind the prior architecture accumulated.

| Item | Consumer |
|---|---|
| `GitSettings.max_blob_bytes` | Milestone 2 ingestion, using `RawTreeEntry.size_bytes`, which `git ls-tree -l` already reports. A guard inside `read_blob` would need a separate `cat-file -s` invocation per file to learn a size the caller already holds. |
| `FileUnit.module_moniker` | Milestone 5 module graph. Present now because the field is part of the specified entity and adding it later would be a migration. |

`CommitManifest` is implemented and tested but not yet produced by any code path:
building it requires file enumeration, which is Milestone 2. It is included in
Milestone 1 because the milestone list specifies the File Unit Model, and a manifest
is the artefact that model exists to populate.

---

## 7. Milestone 2 Preconditions

Milestone 2 (Repository Ingestion) can begin. Its inputs exist:

- `GitClient.list_tree` supplies tree entries with sizes and modes;
- `GitClient.read_blob` and `count_lines` supply content and line counts;
- `ContentAddressableStore.missing` and `put` supply deduplicated storage;
- `FileUnit` and `CommitManifest` supply the target model;
- `FileUnitStore.content_hashes_by_commit` supplies the input to change detection;
- `UnitOfWork` supplies the transaction boundary that makes commit visibility atomic;
- `AdmissionLimits` supplies the stated limits that admission must reject against.

Milestone 2 must add: clone and fetch, file enumeration, the change detector and
diff engine, the durable job queue and worker pool, retry and idempotency around
those jobs, and progress tracking. It must not add anything from Milestone 3 or
later.
