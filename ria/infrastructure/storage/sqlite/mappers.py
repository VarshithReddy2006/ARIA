"""Mapping between domain entities and relational rows.

The single place where domain shapes and persistence shapes meet. SDD open
question T2 records that relational adjacency may have to be replaced on measured
evidence; keeping every translation here means that substitution has exactly one
blast site.

Rules
-----
* Domain to row is total: every field is written, never inferred at read time.
* Row to domain reconstructs through the entity's constructor, so persisted data
  is revalidated on load. A row that violates an invariant fails loudly at read
  rather than propagating a corrupt entity — which matters because SQLite permits
  direct writes by other tools.
* Timestamps round-trip as ISO-8601 with an explicit offset, and are always
  returned timezone-aware in UTC.
* JSON-encoded columns are decoded defensively: a malformed document raises
  :class:`~ria.domain.errors.StorageError` naming the row, rather than yielding a
  partially populated entity.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from ria.domain.enums import (
    BranchCadence,
    CommitIndexState,
    Facet,
    FileClassification,
    JobKind,
    JobState,
    LanguageTier,
    ParseStatus,
    RepositoryStatus,
)
from ria.domain.errors import StorageError
from ria.domain.identity import CommitSha, ContentHash, Moniker, RepositoryId
from ria.domain.models.branch import Branch
from ria.domain.models.commit import (
    ChangeStats,
    Commit,
    CommitCoverage,
    LanguageCoverage,
)
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.job import Job, JobId, RetryPolicy
from ria.domain.models.person import PersonRef
from ria.domain.models.repository import (
    AdmissionLimits,
    IndexPolicy,
    LanguageProfile,
    Repository,
    RetentionPolicy,
    SizeMetrics,
)

__all__ = [
    "repository_to_row",
    "row_to_repository",
    "commit_to_row",
    "row_to_commit",
    "branch_to_row",
    "row_to_branch",
    "file_unit_to_row",
    "row_to_file_unit",
    "job_to_row",
    "row_to_job",
]


# ---------------------------------------------------------------------------
# Primitive conversions
# ---------------------------------------------------------------------------


def _encode_timestamp(value: Optional[datetime]) -> Optional[str]:
    """Encode a datetime as an ISO-8601 string in UTC.

    Args:
        value: Timestamp to encode, or ``None``.

    Returns:
        The encoded string, or ``None``.

    Raises:
        StorageError: If the datetime is naive. Persisting a naive timestamp would
            make every duration computed from it wrong in a way that cannot be
            detected later.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        raise StorageError(
            "refusing to persist a naive datetime", {"value": value.isoformat()}
        )
    return value.astimezone(timezone.utc).isoformat()


def _decode_timestamp(value: Optional[str], *, field: str) -> Optional[datetime]:
    """Decode an ISO-8601 string into a timezone-aware UTC datetime.

    Args:
        value: Encoded timestamp, or ``None``.
        field: Column name, used in the error context.

    Returns:
        The decoded instant, or ``None``.

    Raises:
        StorageError: If the value cannot be parsed.
    """
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StorageError(
            "stored timestamp could not be parsed", {"field": field, "value": value}
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_timestamp(value: Optional[str], *, field: str) -> datetime:
    """Decode a timestamp that must be present.

    Args:
        value: Encoded timestamp.
        field: Column name, used in the error context.

    Returns:
        The decoded instant.

    Raises:
        StorageError: If the value is absent or unparseable.
    """
    decoded = _decode_timestamp(value, field=field)
    if decoded is None:
        raise StorageError("required timestamp is absent", {"field": field})
    return decoded


def _encode_json(payload: Any) -> str:
    """Encode a value as compact, key-sorted JSON.

    Keys are sorted so that an unchanged value produces byte-identical text,
    which keeps row comparisons and change detection meaningful.

    Args:
        payload: Value to encode.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _decode_json(value: Optional[str], *, field: str, default: Any) -> Any:
    """Decode a JSON column, raising on malformed content.

    Args:
        value: Encoded document, or ``None``.
        field: Column name, used in the error context.
        default: Value returned when the column is ``NULL`` or empty.

    Returns:
        The decoded value.

    Raises:
        StorageError: If the document is present but malformed.
    """
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise StorageError(
            "stored JSON column could not be parsed", {"field": field}
        ) from exc


def _enum_of(enum_class: Any, value: str, *, field: str) -> Any:
    """Resolve a stored string to an enum member.

    Args:
        enum_class: Enumeration to resolve against.
        value: Stored value.
        field: Column name, used in the error context.

    Returns:
        The enum member.

    Raises:
        StorageError: If the value is not a member. An unknown state is not
            coerced to a default, because silently reinterpreting a lifecycle
            state would corrupt the timeline.
    """
    try:
        return enum_class(value)
    except ValueError as exc:
        raise StorageError(
            "stored value is not a valid enumeration member",
            {"field": field, "value": value, "enum": enum_class.__name__},
        ) from exc


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


def _index_policy_to_json(policy: IndexPolicy) -> str:
    """Serialise an index policy."""
    return _encode_json(
        {
            "default_branch_cadence": policy.default_branch_cadence.value,
            "feature_branch_cadence": policy.feature_branch_cadence.value,
            "index_pull_requests": policy.index_pull_requests,
            "index_tags": policy.index_tags,
            "stale_branch_days": policy.stale_branch_days,
            "facets": sorted(facet.value for facet in policy.facets),
            "retention": {
                "full_twin_days": policy.retention.full_twin_days,
                "merge_commit_days": policy.retention.merge_commit_days,
                "release_days": policy.retention.release_days,
            },
            "admission": {
                "max_files": policy.admission.max_files,
                "max_file_bytes": policy.admission.max_file_bytes,
                "max_total_bytes": policy.admission.max_total_bytes,
            },
        }
    )


def _index_policy_from_json(payload: Mapping[str, Any]) -> IndexPolicy:
    """Deserialise an index policy.

    Missing keys fall back to the field defaults, which makes the encoding
    forward-compatible: a policy written before a field existed still loads, as
    Twin Spec section 10 requires of additive schema evolution.

    Args:
        payload: Decoded JSON document.

    Raises:
        StorageError: If a stored value is not a valid member or violates a policy
            invariant.
    """
    defaults = IndexPolicy()
    retention = payload.get("retention") or {}
    admission = payload.get("admission") or {}
    try:
        return IndexPolicy(
            default_branch_cadence=_enum_of(
                BranchCadence,
                payload.get(
                    "default_branch_cadence", defaults.default_branch_cadence.value
                ),
                field="index_policy.default_branch_cadence",
            ),
            feature_branch_cadence=_enum_of(
                BranchCadence,
                payload.get(
                    "feature_branch_cadence", defaults.feature_branch_cadence.value
                ),
                field="index_policy.feature_branch_cadence",
            ),
            index_pull_requests=bool(
                payload.get("index_pull_requests", defaults.index_pull_requests)
            ),
            index_tags=bool(payload.get("index_tags", defaults.index_tags)),
            stale_branch_days=int(
                payload.get("stale_branch_days", defaults.stale_branch_days)
            ),
            facets=frozenset(
                _enum_of(Facet, name, field="index_policy.facets")
                for name in payload.get(
                    "facets", sorted(facet.value for facet in defaults.facets)
                )
            ),
            retention=RetentionPolicy(
                full_twin_days=int(
                    retention.get("full_twin_days", defaults.retention.full_twin_days)
                ),
                merge_commit_days=int(
                    retention.get(
                        "merge_commit_days", defaults.retention.merge_commit_days
                    )
                ),
                release_days=int(
                    retention.get("release_days", defaults.retention.release_days)
                ),
            ),
            admission=AdmissionLimits(
                max_files=int(admission.get("max_files", defaults.admission.max_files)),
                max_file_bytes=int(
                    admission.get("max_file_bytes", defaults.admission.max_file_bytes)
                ),
                max_total_bytes=int(
                    admission.get("max_total_bytes", defaults.admission.max_total_bytes)
                ),
            ),
        )
    except (TypeError, ValueError) as exc:
        raise StorageError(
            "stored index policy is invalid", {"reason": str(exc)}
        ) from exc


def _languages_to_json(profiles: Tuple[LanguageProfile, ...]) -> str:
    """Serialise language profiles."""
    return _encode_json(
        [
            {
                "language": profile.language,
                "loc": profile.loc,
                "percentage": profile.percentage,
                "tier": profile.tier.value,
                "precision": profile.precision,
            }
            for profile in profiles
        ]
    )


def _languages_from_json(payload: Any) -> Tuple[LanguageProfile, ...]:
    """Deserialise language profiles.

    Raises:
        StorageError: If an entry is malformed.
    """
    try:
        return tuple(
            LanguageProfile(
                language=entry["language"],
                loc=int(entry["loc"]),
                percentage=float(entry["percentage"]),
                tier=_enum_of(LanguageTier, entry["tier"], field="languages.tier"),
                precision=(
                    float(entry["precision"])
                    if entry.get("precision") is not None
                    else None
                ),
            )
            for entry in payload
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StorageError(
            "stored language profile is invalid", {"reason": str(exc)}
        ) from exc


def _size_metrics_to_json(metrics: SizeMetrics) -> str:
    """Serialise size metrics."""
    return _encode_json(
        {
            "files": metrics.files,
            "loc": metrics.loc,
            "symbols": metrics.symbols,
            "edges": metrics.edges,
            "measured_at": _encode_timestamp(metrics.measured_at),
            "measured_at_sha": metrics.measured_at_sha,
        }
    )


def _size_metrics_from_json(payload: Mapping[str, Any]) -> SizeMetrics:
    """Deserialise size metrics.

    Raises:
        StorageError: If a value is malformed.
    """
    try:
        return SizeMetrics(
            files=payload.get("files"),
            loc=payload.get("loc"),
            symbols=payload.get("symbols"),
            edges=payload.get("edges"),
            measured_at=_decode_timestamp(
                payload.get("measured_at"), field="size_metrics.measured_at"
            ),
            measured_at_sha=payload.get("measured_at_sha"),
        )
    except (TypeError, ValueError) as exc:
        raise StorageError(
            "stored size metrics are invalid", {"reason": str(exc)}
        ) from exc


def repository_to_row(repository: Repository) -> Dict[str, Any]:
    """Convert a repository to its row representation.

    Args:
        repository: Entity to convert.

    Returns:
        A column-name to value mapping.
    """
    return {
        "repository_id": str(repository.repository_id),
        "moniker": str(repository.moniker),
        "origin_url": repository.origin_url,
        "default_branch": repository.default_branch,
        "tenant_id": repository.tenant_id,
        "status": repository.status.value,
        "degraded_reason": repository.degraded_reason,
        "index_policy": _index_policy_to_json(repository.index_policy),
        "languages": _languages_to_json(repository.languages),
        "frameworks": _encode_json(list(repository.frameworks)),
        "size_metrics": _size_metrics_to_json(repository.size_metrics),
        "registered_at": _encode_timestamp(repository.registered_at),
        "updated_at": _encode_timestamp(repository.updated_at),
        "last_indexed_at": _encode_timestamp(repository.last_indexed_at),
        "last_indexed_sha": repository.last_indexed_sha,
    }


def row_to_repository(row: sqlite3.Row) -> Repository:
    """Reconstruct a repository from its row representation.

    Args:
        row: Row from ``ria_repository``.

    Returns:
        The entity.

    Raises:
        StorageError: If the row cannot produce a valid entity.
    """
    try:
        return Repository(
            repository_id=RepositoryId.parse(row["repository_id"]),
            moniker=Moniker.parse(row["moniker"]),
            origin_url=row["origin_url"],
            default_branch=row["default_branch"],
            tenant_id=row["tenant_id"],
            status=_enum_of(RepositoryStatus, row["status"], field="status"),
            degraded_reason=row["degraded_reason"],
            index_policy=_index_policy_from_json(
                _decode_json(row["index_policy"], field="index_policy", default={})
            ),
            languages=_languages_from_json(
                _decode_json(row["languages"], field="languages", default=[])
            ),
            frameworks=tuple(
                _decode_json(row["frameworks"], field="frameworks", default=[])
            ),
            size_metrics=_size_metrics_from_json(
                _decode_json(row["size_metrics"], field="size_metrics", default={})
            ),
            registered_at=_require_timestamp(
                row["registered_at"], field="registered_at"
            ),
            updated_at=_require_timestamp(row["updated_at"], field="updated_at"),
            last_indexed_at=_decode_timestamp(
                row["last_indexed_at"], field="last_indexed_at"
            ),
            last_indexed_sha=row["last_indexed_sha"],
        )
    except (ValueError, TypeError) as exc:
        raise StorageError(
            "stored repository row is invalid",
            {"repository_id": row["repository_id"], "reason": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------


def _coverage_to_json(coverage: Optional[CommitCoverage]) -> Optional[str]:
    """Serialise commit coverage, preserving the distinction between unmeasured
    (``None``) and measured-as-zero."""
    if coverage is None:
        return None
    return _encode_json(
        {
            "files_total": coverage.files_total,
            "files_eligible": coverage.files_eligible,
            "files_parsed": coverage.files_parsed,
            "symbols_total": coverage.symbols_total,
            "symbols_resolved": coverage.symbols_resolved,
            "exact_edges": coverage.exact_edges,
            "total_edges": coverage.total_edges,
            "by_language": [
                {
                    "language": entry.language,
                    "files_total": entry.files_total,
                    "files_parsed": entry.files_parsed,
                    "symbols_total": entry.symbols_total,
                    "symbols_resolved": entry.symbols_resolved,
                    "exact_edges": entry.exact_edges,
                    "total_edges": entry.total_edges,
                }
                for entry in coverage.by_language
            ],
        }
    )


def _coverage_from_json(value: Optional[str]) -> Optional[CommitCoverage]:
    """Deserialise commit coverage.

    Raises:
        StorageError: If the document is malformed.
    """
    payload = _decode_json(value, field="coverage", default=None)
    if payload is None:
        return None
    try:
        return CommitCoverage(
            files_total=int(payload["files_total"]),
            files_eligible=int(payload["files_eligible"]),
            files_parsed=int(payload["files_parsed"]),
            symbols_total=payload.get("symbols_total"),
            symbols_resolved=payload.get("symbols_resolved"),
            exact_edges=payload.get("exact_edges"),
            total_edges=payload.get("total_edges"),
            by_language=tuple(
                LanguageCoverage(
                    language=entry["language"],
                    files_total=int(entry["files_total"]),
                    files_parsed=int(entry["files_parsed"]),
                    symbols_total=entry.get("symbols_total"),
                    symbols_resolved=entry.get("symbols_resolved"),
                    exact_edges=entry.get("exact_edges"),
                    total_edges=entry.get("total_edges"),
                )
                for entry in payload.get("by_language", [])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StorageError("stored coverage is invalid", {"reason": str(exc)}) from exc


def commit_to_row(commit: Commit) -> Dict[str, Any]:
    """Convert a commit to its row representation.

    The fact fingerprint is computed here and stored alongside the facts, which is
    what allows the adapter to detect an attempted rewrite.

    Args:
        commit: Entity to convert.

    Returns:
        A column-name to value mapping.
    """
    return {
        "repository_id": str(commit.repository_id),
        "sha": str(commit.sha),
        "parents": _encode_json([str(parent) for parent in commit.parents]),
        "tree_hash": commit.tree_hash,
        "author_name": commit.author.name,
        "author_email": commit.author.email,
        "committer_name": commit.committer.name,
        "committer_email": commit.committer.email,
        "authored_at": _encode_timestamp(commit.authored_at),
        "committed_at": _encode_timestamp(commit.committed_at),
        "message": commit.message,
        "files_changed": commit.change_stats.files_changed,
        "insertions": commit.change_stats.insertions,
        "deletions": commit.change_stats.deletions,
        "index_state": commit.index_state.value,
        "failure_reason": commit.failure_reason,
        "coverage": _coverage_to_json(commit.coverage),
        "indexed_at": _encode_timestamp(commit.indexed_at),
        "facts_fingerprint": commit.facts_fingerprint(),
    }


def row_to_commit(row: sqlite3.Row) -> Commit:
    """Reconstruct a commit from its row representation.

    Args:
        row: Row from ``ria_commit``.

    Returns:
        The entity.

    Raises:
        StorageError: If the row cannot produce a valid entity.
    """
    try:
        return Commit(
            repository_id=RepositoryId.parse(row["repository_id"]),
            sha=CommitSha(row["sha"]),
            parents=tuple(
                CommitSha(value)
                for value in _decode_json(row["parents"], field="parents", default=[])
            ),
            author=PersonRef(name=row["author_name"], email=row["author_email"]),
            committer=PersonRef(
                name=row["committer_name"], email=row["committer_email"]
            ),
            authored_at=_require_timestamp(row["authored_at"], field="authored_at"),
            committed_at=_require_timestamp(row["committed_at"], field="committed_at"),
            message=row["message"],
            tree_hash=row["tree_hash"],
            change_stats=ChangeStats(
                files_changed=row["files_changed"],
                insertions=row["insertions"],
                deletions=row["deletions"],
            ),
            index_state=_enum_of(
                CommitIndexState, row["index_state"], field="index_state"
            ),
            coverage=_coverage_from_json(row["coverage"]),
            indexed_at=_decode_timestamp(row["indexed_at"], field="indexed_at"),
            failure_reason=row["failure_reason"],
        )
    except (ValueError, TypeError) as exc:
        raise StorageError(
            "stored commit row is invalid",
            {
                "repository_id": row["repository_id"],
                "sha": row["sha"],
                "reason": str(exc),
            },
        ) from exc


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------


def branch_to_row(branch: Branch) -> Dict[str, Any]:
    """Convert a branch to its row representation.

    Args:
        branch: Entity to convert.

    Returns:
        A column-name to value mapping.
    """
    return {
        "repository_id": str(branch.repository_id),
        "name": branch.name,
        "head_sha": str(branch.head_sha),
        "is_default": 1 if branch.is_default else 0,
        "is_protected": 1 if branch.is_protected else 0,
        "last_commit_at": _encode_timestamp(branch.last_commit_at),
        "updated_at": _encode_timestamp(branch.updated_at),
        "merge_base_cache": _encode_json(dict(branch.merge_base_cache)),
    }


def row_to_branch(row: sqlite3.Row) -> Branch:
    """Reconstruct a branch from its row representation.

    Args:
        row: Row from ``ria_branch``.

    Returns:
        The entity.

    Raises:
        StorageError: If the row cannot produce a valid entity.
    """
    try:
        return Branch(
            repository_id=RepositoryId.parse(row["repository_id"]),
            name=row["name"],
            head_sha=CommitSha(row["head_sha"]),
            updated_at=_require_timestamp(row["updated_at"], field="updated_at"),
            is_default=bool(row["is_default"]),
            is_protected=bool(row["is_protected"]),
            last_commit_at=_decode_timestamp(
                row["last_commit_at"], field="last_commit_at"
            ),
            merge_base_cache=_decode_json(
                row["merge_base_cache"], field="merge_base_cache", default={}
            ),
        )
    except (ValueError, TypeError) as exc:
        raise StorageError(
            "stored branch row is invalid",
            {
                "repository_id": row["repository_id"],
                "name": row["name"],
                "reason": str(exc),
            },
        ) from exc


# ---------------------------------------------------------------------------
# FileUnit
# ---------------------------------------------------------------------------


def file_unit_to_row(unit: FileUnit) -> Dict[str, Any]:
    """Convert a file unit to its row representation.

    Args:
        unit: Entity to convert.

    Returns:
        A column-name to value mapping.
    """
    return {
        "repository_id": str(unit.repository_id),
        "commit_sha": str(unit.commit_sha),
        "path": unit.path,
        "content_hash": str(unit.content_hash),
        "blob_sha": unit.blob_sha,
        "language": unit.language,
        "language_tier": unit.language_tier.value,
        "size_bytes": unit.size_bytes,
        "line_count": unit.line_count,
        "classification": unit.classification.value,
        "parse_status": unit.parse_status.value,
        "parse_status_reason": unit.parse_status_reason,
        "module_moniker": str(unit.module_moniker) if unit.module_moniker else None,
    }


def row_to_file_unit(row: sqlite3.Row) -> FileUnit:
    """Reconstruct a file unit from its row representation.

    Args:
        row: Row from ``ria_file_unit``.

    Returns:
        The entity.

    Raises:
        StorageError: If the row cannot produce a valid entity.
    """
    try:
        return FileUnit(
            repository_id=RepositoryId.parse(row["repository_id"]),
            commit_sha=CommitSha(row["commit_sha"]),
            path=row["path"],
            content_hash=ContentHash(row["content_hash"]),
            blob_sha=row["blob_sha"],
            language=row["language"],
            language_tier=_enum_of(
                LanguageTier, row["language_tier"], field="language_tier"
            ),
            size_bytes=row["size_bytes"],
            line_count=row["line_count"],
            classification=_enum_of(
                FileClassification, row["classification"], field="classification"
            ),
            parse_status=_enum_of(
                ParseStatus, row["parse_status"], field="parse_status"
            ),
            parse_status_reason=row["parse_status_reason"],
            module_moniker=(
                Moniker.parse(row["module_moniker"]) if row["module_moniker"] else None
            ),
        )
    except (ValueError, TypeError) as exc:
        raise StorageError(
            "stored file unit row is invalid",
            {
                "repository_id": row["repository_id"],
                "commit_sha": row["commit_sha"],
                "path": row["path"],
                "reason": str(exc),
            },
        ) from exc


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


def _retry_policy_to_json(policy: RetryPolicy) -> str:
    """Encode a retry policy as JSON.

    Stored as a document rather than as columns because it is read and written whole
    by one owner, is never filtered on, and gains fields additively.

    Args:
        policy: Policy to encode.
    """
    return _encode_json(
        {
            "max_attempts": policy.max_attempts,
            "base_delay_seconds": policy.base_delay_seconds,
            "multiplier": policy.multiplier,
            "max_delay_seconds": policy.max_delay_seconds,
            "jitter_ratio": policy.jitter_ratio,
        }
    )


def _retry_policy_from_json(payload: Mapping[str, Any]) -> RetryPolicy:
    """Rebuild a retry policy from its stored document.

    Unknown keys are ignored and absent keys fall back to the class default, so a
    document written by an older version remains loadable (Twin Spec section 10,
    additive schema evolution).

    Args:
        payload: Decoded document.

    Raises:
        StorageError: If a present value is of the wrong type or violates a policy
            invariant.
    """
    default = RetryPolicy()
    try:
        return RetryPolicy(
            max_attempts=int(payload.get("max_attempts", default.max_attempts)),
            base_delay_seconds=float(
                payload.get("base_delay_seconds", default.base_delay_seconds)
            ),
            multiplier=float(payload.get("multiplier", default.multiplier)),
            max_delay_seconds=float(
                payload.get("max_delay_seconds", default.max_delay_seconds)
            ),
            jitter_ratio=float(payload.get("jitter_ratio", default.jitter_ratio)),
        )
    except (TypeError, ValueError) as exc:
        raise StorageError(
            "stored retry policy is invalid", {"payload": dict(payload)}
        ) from exc


def _job_payload_from_json(value: Optional[str]) -> Dict[str, str]:
    """Decode a job payload, enforcing that every value is a string.

    The port declares string values only so that no adapter needs a type registry.
    Enforcing it here means a document written directly through another SQLite client
    cannot smuggle a nested structure into a handler.

    Args:
        value: Encoded document.

    Raises:
        StorageError: If the document is not a flat mapping of strings.
    """
    payload = _decode_json(value, field="payload", default={})
    if not isinstance(payload, dict):
        raise StorageError("stored job payload is not an object", {"payload": payload})
    decoded: Dict[str, str] = {}
    for key, item in payload.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise StorageError(
                "stored job payload must map strings to strings",
                {"key": key, "value": item},
            )
        decoded[key] = item
    return decoded


def job_to_row(job: Job) -> Dict[str, Any]:
    """Convert a job to its relational row.

    Args:
        job: Job to convert.

    Returns:
        Column name to value mapping.
    """
    return {
        "job_id": str(job.job_id),
        "repository_id": str(job.repository_id),
        "kind": job.kind.value,
        "idempotency_key": job.idempotency_key,
        "payload": _encode_json(dict(job.payload)),
        "state": job.state.value,
        "priority": job.priority,
        "attempts": job.attempts,
        "retry_policy": _retry_policy_to_json(job.retry_policy),
        "available_at": _encode_timestamp(job.available_at),
        "created_at": _encode_timestamp(job.created_at),
        "updated_at": _encode_timestamp(job.updated_at),
        "leased_until": _encode_timestamp(job.leased_until),
        "lease_owner": job.lease_owner,
        "stage": job.stage,
        "last_error": job.last_error,
    }


def row_to_job(row: sqlite3.Row) -> Job:
    """Reconstruct a job from its relational row.

    Args:
        row: Row to convert.

    Returns:
        The job.

    Raises:
        StorageError: If a stored value is malformed or violates an invariant.
    """
    return Job(
        job_id=JobId.parse(row["job_id"]),
        repository_id=RepositoryId.parse(row["repository_id"]),
        kind=_enum_of(JobKind, row["kind"], field="kind"),
        idempotency_key=row["idempotency_key"],
        payload=_job_payload_from_json(row["payload"]),
        state=_enum_of(JobState, row["state"], field="state"),
        priority=int(row["priority"]),
        attempts=int(row["attempts"]),
        retry_policy=_retry_policy_from_json(
            _decode_json(row["retry_policy"], field="retry_policy", default={})
        ),
        available_at=_require_timestamp(row["available_at"], field="available_at"),
        created_at=_require_timestamp(row["created_at"], field="created_at"),
        updated_at=_require_timestamp(row["updated_at"], field="updated_at"),
        leased_until=_decode_timestamp(row["leased_until"], field="leased_until"),
        lease_owner=row["lease_owner"],
        stage=row["stage"],
        last_error=row["last_error"],
    )
