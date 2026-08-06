# Milestone 2 — Repository Ingestion

**Status:** complete
**Implements:** SDD section 3 (L1 Ingestion) end to end, plus the cross-cutting
Orchestration seam of SDD section 2.1 that the brief's layering omits.
**Package:** `ria/`
**Tests:** 888 measured total (650 unit, 238 integration); 230 of them cover Milestone 2

---

## 1. Scope

| Item | Where |
|---|---|
| Clone | `GitClient.clone_mirror` → `SubprocessGitClient` |
| Fetch | `GitClient.fetch` → `SubprocessGitClient` |
| Commit Discovery | `ria/application/commit_discovery.py` |
| Branch Discovery | `CommitDiscovery._observe_branches`, `BranchStore.replace_all` |
| Change Detection | `ria/domain/diff.py` |
| Diff Engine | `compute_change_set`, `ria/domain/models/change_set.py` |
| File Enumeration | `ria/application/file_enumerator.py` |
| Content Hashing | `FileEnumerator._stream_hash`, `ContentHash.of_stream` |
| Blob Store | `FilesystemBlobStore` (Milestone 1), consumed here |
| Ingestion Workers | `ria/application/job_runner.py` |
| Retry Logic | `RetryPolicy`, `JobRunner._fail` |
| Idempotency | `ria_job` unique index, `JobStore.enqueue`, `IngestionService` short-circuit |
| Job Queue | `ria/ports/job_store.py`, `job_repository.py`, `0002_ingestion.sql` |
| Progress Tracking | `ProgressEvent`, `ProgressSink`, four sinks |
| Observability | Metrics and structured logging throughout |
| Orchestration | `ria/application/ingestion_service.py` |
| Handler registry | `ria/application/ingestion_handlers.py` |

Nothing from Milestone 3 or later is present. No parser exists, and the coverage
report says so: `files_parsed` is always zero.

---

## 2. Subsystems

### 2.1 Mirror Manager — `ria/application/mirror_manager.py`

**Purpose.** Create, refresh and locate local bare mirrors of registered repositories.

**Responsibilities.** Derive a mirror path from a moniker; clone; fetch; report whether
a mirror is usable; discard one.

**Dependencies.** `GitClient`, the mirror root from settings, `MetricsSink`.

**Data flow.** `Repository` → `MirrorState { path, was_cloned, was_fetched }`. The path
is derived from the moniker rather than stored, so the mapping is reproducible and no
extra state can drift out of step with it.

**Failure modes.** `GitCommandError` on an unreachable origin or expired credentials;
`MirrorNotFoundError` from `require` when no mirror is present. A directory that exists
but is not a usable mirror is cleared and re-cloned rather than fetched into.

**Extension points.** A different VCS is a new adapter behind the same port. Mirrors are
a cache of upstream truth (SDD section 6.2) and may be deleted at any time.

### 2.2 Commit Discovery — `ria/application/commit_discovery.py`

**Purpose.** Record the branch set and the commits reachable from a ref, and enqueue one
ingestion job per commit that needs building.

**Responsibilities.** Observe branches; walk history under the repository's snapshot
cadence policy; skip commits already queryable; enqueue ingestion work; report progress.

**Dependencies.** `GitClient`, `UnitOfWorkFactory`, `Clock`, `MetricsSink`,
`ProgressSink`, a `RetryPolicy` for the jobs it creates.

**Data flow.** `ref` → `list_commits` → cadence filter → `DiscoveryResult`. Branches and
jobs are written in one transaction, so a crash cannot leave a refreshed branch set with
no work to process it.

**Failure modes.** `RepositoryNotFoundError`; `MirrorNotFoundError`; `GitCommandError`.
Re-running is a no-op: already-indexed commits are skipped before a job is created, and
the job's idempotency key means a duplicate enqueue returns the existing job.

**Extension points.** Cadence is policy data on the repository, not logic here, so a new
cadence is a new enum member plus a filter clause.

### 2.3 File Enumerator — `ria/application/file_enumerator.py`

**Purpose.** Turn a git tree into a `CommitManifest`, storing content the system will
read again.

**Responsibilities.** List the tree; enforce admission limits before reading anything;
classify and detect language; decide per blob whether to store, read or stream it; hash
content; build file units; report progress.

**Dependencies.** `GitClient`, `ContentAddressableStore`, `LanguageCatalogue`, `Clock`,
`MetricsSink`, `ProgressSink`, a memory limit.

**Data flow.** `RawTreeEntry[]` → classification → storage plan → `EnumerationResult
{ manifest, blobs_stored, blobs_reused, blobs_streamed, bytes_read }`.

**Failure modes.** `AdmissionRejectedError` before any content is read;
`RefNotFoundError`; `GitCommandError`; `StorageError`. A malformed tree record is logged
and skipped rather than aborting the listing, per the L1 rule that one bad file must not
fail a build.

**Extension points.** Blobs above the memory limit are hashed by streaming rather than
buffered, so the admission limit governs disk rather than memory.

**Design note.** The enumerator sets `parent_shas=()` on the manifest it builds. It reads
a *tree* and cannot know ancestry; `IngestionService` rebuilds the manifest with the
commit's parents so that the artefact describes a commit rather than a tree. Without
that, the manifest could not be diffed against a base.

### 2.4 Change Detection — `ria/domain/diff.py`

**Purpose.** Compare two commit trees by content hash.

**Responsibilities.** Categorise every path as added, modified, deleted or renamed.

**Dependencies.** None. A pure function over two mappings, which is why it is testable in
microseconds and why the same implementation serves ingestion now and pull request
diffing later.

**Data flow.** Two `path -> content_hash` mappings → `ChangeSet`. Categories are
disjoint, enforced at construction.

**Failure modes.** `ValueError` if a previous tree is supplied without naming its base
commit, or vice versa: a change set that cannot name its base is not interpretable.

**Extension points.** Rename detection is exact content-hash equality, not similarity.
The rule is narrower than git's `-M` heuristic on purpose: a rename claimed here means
the parse cache is definitely reusable, whereas a similarity-based rename would not and
would silently skip a reparse the content required.

### 2.5 Job Queue — `ria/ports/job_store.py`, `job_repository.py`, `0002_ingestion.sql`

**Purpose.** Durable, lease-based work queue with priority, retry and idempotency.

**Responsibilities.** Enqueue idempotently; claim the most urgent available job; persist
transitions; reclaim lapsed leases; report depth; cancel a repository's pending work.

**Dependencies.** The unit of work's SQLite connection. The adapter deliberately does not
open its own connection: the claim must share a transaction with the caller's other
writes, or the exclusivity guarantee is lost.

**Data flow.** `Job` → row → `Job`. Retry policy and payload are JSON documents, read and
written whole by one owner.

**Failure modes.** `StorageError`; `JobNotFoundError`. Two check constraints defend the
queue against direct writes through another client: a leased row must carry both a
deadline and an owner, and a dead row must carry a reason. A lease with no deadline would
never expire and would stall the queue forever.

**Extension points.** New job kinds are enum members; the claim query filters by kind, so
a deployment can run dedicated workers without a second queue.

**Design note.** Two workers never receive one job because the select and the update
occur inside the write transaction SQLite acquires at `BEGIN IMMEDIATE`. Idempotency is a
unique index rather than a check-then-insert, because a read followed by a write is not
atomic and two simultaneous enqueues of one key would both pass the check.

### 2.6 Job Runner — `ria/application/job_runner.py`

**Purpose.** Lease a job, dispatch it, and record the outcome.

**Responsibilities.** Claim work this worker can handle; dispatch; classify failures;
apply backoff or dead-letter; reclaim lapsed leases; publish queue depth.

**Dependencies.** `UnitOfWorkFactory`, `Clock`, `MetricsSink`, a handler per job kind, a
randomness source for jitter.

**Data flow.** `lease → handler → JobOutcome`. A handler returns nothing; the outcome is
success unless it raises, which keeps handlers free of the queue's vocabulary.

**Failure modes.** Every path records something. A handler exception becomes a `FAILED`
transition carrying the reason, then a requeue with backoff or a dead letter. A job kind
with no handler is dead-lettered immediately rather than left to be leased forever by
workers that cannot run it.

**Extension points.** `run_once` plus a caller-driven loop rather than a self-managed
thread, so the caller owns shutdown and a process drains by simply not calling again.
`drain`'s bound is mandatory because a handler may enqueue further work.

**Design note.** The retry decision belongs to the runner, not the handler: only the
runner knows the attempt count, the policy and the clock. A domain error's own
`is_retryable` classification is authoritative and is *not* widened by remaining
attempts — see section 4.

### 2.7 Ingestion Service — `ria/application/ingestion_service.py`

**Purpose.** Compose the pipeline for one commit and make it queryable atomically.

**Responsibilities.** Locate the mirror; resolve and record the commit; advance the
repository and commit lifecycles; enumerate; detect changes; persist; finalise; record
failure honestly.

**Dependencies.** `MirrorManager`, `CommitResolver`, `FileEnumerator`,
`UnitOfWorkFactory`, `Clock`, `MetricsSink`, `ProgressSink`.

**Data flow.** `Repository` + ref → `IngestionResult { commit, manifest, change_set,
coverage, blobs_stored, blobs_reused }`.

**Failure modes.** `MirrorNotFoundError`, `AdmissionRejectedError`, `RefNotFoundError`,
`StorageError`. On any failure the commit is transitioned to `FAILED` with the reason and
the exception re-raised; a failure to record the failure is logged rather than raised, so
the original cause is not replaced by a storage error.

**Extension points.** Stages are named and timed individually, so Milestone 3 inserts
parsing between `ENUMERATE` and `PERSIST` without touching the others.

**Design notes.**

*Atomic visibility.* File units, coverage and the `QUERYABLE` transition are one
transaction (SDD section 5.1 step 9). A half-built index "produces answers that are wrong
in ways indistinguishable from right".

*Idempotency.* An already-queryable commit short-circuits before any git access. A forced
rebuild deletes the commit's file units before rewriting them, so a previous attempt that
died mid-write converges rather than colliding on the primary key.

*No implicit clone.* Ingestion requires a mirror and never creates one. Acquisition is a
separate job kind because the two have different failure modes and would otherwise share
one retry schedule.

### 2.8 Progress Reporting — `ria/domain/models/progress.py`, four sinks

**Purpose.** Make a multi-minute ingestion observable.

**Responsibilities.** Model one observation as a value object; fan out to logs, memory or
several destinations.

**Dependencies.** None in the domain; the sinks depend only on the standard library.

**Data flow.** `ProgressEvent { repository_id, stage, completed, total, message }` →
`ProgressSink`.

**Failure modes.** None propagate. A composite sink isolates a failing delegate, because
an observability fault must not fail an index build.

**Extension points.** `total` is `Optional` and is `None` until known, so a stage that has
not yet counted its work does not report a fabricated total that would make a progress
bar jump backwards. HTTP streaming is a delivery-layer sink composed over these.

### 2.9 Handler Registry — `ria/application/ingestion_handlers.py`

**Purpose.** Bind each job kind to the use case that performs it.

**Responsibilities.** Load the repository; refuse withdrawn repositories; parse payload
arguments strictly; delegate.

**Dependencies.** `RepositoryManager`, `MirrorManager`, `CommitDiscovery`,
`IngestionService`, `MetricsSink`.

**Failure modes.** `RepositoryNotFoundError`; `ApplicationError` for a withdrawn
repository or a malformed payload. Both are non-retryable, so the runner dead-letters
rather than spending the attempt budget on a state only an operator can change.

**Extension points.** The mapping is application logic, not container wiring, so a test
can assemble handlers over fakes without building a container.

**Design note.** Every handler reloads the repository on each attempt rather than
capturing it at enqueue time. A job enqueued an hour ago must honour the configuration as
it is now: if an operator tightened an admission limit or paused the repository, the
attempt must respect that.

---

## 3. Incident: reconstructed entities

During this milestone I overwrote `ria/domain/models/change_set.py` and
`ria/domain/models/job.py` with different designs before checking that the surrounding
Milestone 2 code already existed. `ria/` was untracked, so git could not restore them.

Both files were reconstructed from their consumers — `mappers.py`, `0002_ingestion.sql`,
`job_store.py` and `commit_discovery.py` gave the exact field sets, method names and
constructor signatures — and now match the surface the surrounding code was written
against: `ChangeSet(head_sha, base_sha, added, modified, deleted, renamed)` with
`RenamedPath`; `Job` with its sixteen persisted fields; `JobId` as a value object;
`RetryPolicy(max_attempts, base_delay_seconds, multiplier, max_delay_seconds,
jitter_ratio)`. `JobKind`, `JobState`, `JOB_TRANSITIONS`, `ChangeKind` and
`IngestionStage` remain in `ria/domain/enums.py` where they already lived.

The reconstruction is inferred from consumers rather than restored, so the docstrings and
any invariants those files carried are new. The 107 tests now covering the two modules are
what establishes their behaviour.

---

## 4. Defects found and fixed

Five, three of them by tests written against the specification rather than the code.

| Defect | Consequence if shipped | Fix |
|---|---|---|
| Repository lifecycle never advanced | A fully successful first ingestion left the repository `REGISTERED` with `last_indexed_sha` unset, because `ACTIVE` is unreachable from `REGISTERED`. A status query would show a never-indexed repository whose commits were queryable | `IngestionService._mark_repository_indexing` promotes `REGISTERED\|ACTIVE\|DEGRADED → INDEXING` before a build, leaving paused and archived repositories alone |
| `Job.leased` permitted re-leasing a leased job | `assert_transition` treats a self-transition as an idempotent no-op, correct for a commit re-asserting its state but here it would let a second worker claim a job already held — the one outcome leasing exists to prevent | Explicit `state is not QUEUED` guard before the table check |
| `retryable=exc.is_retryable or job.can_retry` | Every permanent fault became retryable while any attempt remained, spending the whole budget on malformed payloads and withdrawn repositories | The error's own classification is authoritative; the attempt ceiling is applied separately in `_fail` |
| `FakeGitClient` missing four port methods | The double had drifted from the port, so a unit test could pass on behaviour the real adapter lacks | Implemented `open_blob`, `clone_mirror`, `fetch`, `list_commits`; added `test_port_conformance.py` so the drift cannot recur |
| `InMemoryUnitOfWork` missing `jobs` | Same class of drift, introduced when the port gained the store | Added `InMemoryJobStore`, which also reproduces enqueue idempotency and total claim ordering |

The last two are the same defect twice. `tests/ria/unit/test_port_conformance.py` now
asserts every double and every cheaply-constructible adapter against its port, which is
why the second instance was caught within a minute of the first being fixed.

---

## 5. Verification

```bash
pytest tests/ria -q                              # 888 passed
pytest tests/ria/unit -q                         # 650 in 0.6s — no filesystem, database or subprocess
pytest tests/ria/integration -q                  # 238 — real adapters

pytest tests/ria/unit/test_domain_job.py -q      # 72  — lifecycle, leasing, backoff
pytest tests/ria/unit/test_diff.py -q            # 35  — change set invariants, rename pairing
pytest tests/ria/unit/test_job_runner.py -q      # 35  — retry, dead-letter, reclaim
pytest tests/ria/unit/test_ingestion_handlers.py # 23  — payload strictness, withdrawal guard
pytest tests/ria/integration/test_job_store.py   # 25  — claim, idempotency index, constraints
pytest tests/ria/integration/test_ingestion.py   # 26  — end to end against real git

ruff check .                                     # All checks passed
ruff format --check .                            # clean
pytest -q                                        # full repository, no regression
```

Environments without a git executable skip the git-dependent tests via
`tests.ria.conftest.requires_git`; everything else still runs.

### Properties the integration suite establishes

- **Atomic visibility.** A rejected commit leaves zero file units and no queryable
  commit; the commit is `FAILED` with a stated reason.
- **Deduplication.** Three identical files cost one stored blob.
- **Incremental reuse.** A one-file edit reports `blobs_reused ≥ 1` and a non-zero reuse
  ratio.
- **Exact rename detection.** A moved file appears as a rename, is absent from
  `paths_requiring_reparse`, and its old path is present in `paths_to_invalidate`.
- **Idempotency.** Re-ingesting a queryable commit stores nothing and reports
  `was_already_indexed`; a forced rebuild preserves the commit's fact fingerprint.
- **Queue-driven pipeline.** Three job kinds carry a repository from registration to
  `ACTIVE` with one queryable commit and two recorded branches.
- **Worker failure recovery.** A lapsed lease returns the job to the queue and another
  worker claims it.
- **Withdrawal.** Pausing a repository dead-letters its queued work rather than retrying.

---

## 6. Milestone 3 preconditions

The parser layer's inputs exist:

- `CommitManifest.parse_candidates()` selects the units to extract from;
- `FileUnit.reuse_key` is the content-plus-language cache key, awaiting the extractor
  version the parser layer owns;
- `ChangeSet.paths_requiring_reparse()` bounds incremental parsing and already excludes
  renames;
- `ContentAddressableStore` holds the bytes, keyed by digest;
- `CommitCoverage` has the `files_parsed`, `symbols_total` and `by_language` fields the
  parser must populate — currently zero and `None`, honestly;
- `LanguageTier` declares `TIER_A`/`TIER_B` per language, all `NONE` until an extractor
  with fixture-backed precision tests lands;
- `IngestionStage` has no parse stage yet; adding one is an explicit edit to
  `_INGESTION_STAGE_ORDER`.

Milestone 3 must add tree-sitter integration, the language plugin architecture, extractor
interfaces, AST generation, the query engine, parse caching, incremental parsing, and the
parser and capability registries. Per PRD principle P8 no language may be promoted above
`LanguageTier.NONE` without a committed, measured precision figure.
