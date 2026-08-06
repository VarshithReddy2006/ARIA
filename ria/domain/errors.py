"""Domain error hierarchy.

Every error raised by ``ria`` derives from :class:`RiaError`, which allows a
delivery layer to translate the whole tree into transport-specific responses
without importing individual error types.

The hierarchy separates three concerns:

* :class:`DomainError` — an invariant defined in the specifications was
  violated. Always a programming or data-integrity fault, never transient.
* :class:`ApplicationError` — a use case could not complete because of the
  state of the system (missing entity, duplicate registration). Expected and
  actionable by the caller.
* :class:`InfrastructureError` — an adapter failed (git, filesystem,
  database). May be transient and therefore retryable; ``is_retryable``
  states which.

Design note
-----------
Errors carry structured context rather than only a message, so that log
records and metrics labels can be derived without re-parsing prose.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

__all__ = [
    "RiaError",
    "DomainError",
    "InvalidMonikerError",
    "InvalidContentHashError",
    "InvalidCommitShaError",
    "InvalidPathError",
    "IllegalStateTransitionError",
    "ImmutableFactViolationError",
    "ApplicationError",
    "RepositoryAlreadyExistsError",
    "RepositoryNotFoundError",
    "CommitNotFoundError",
    "BranchNotFoundError",
    "JobNotFoundError",
    "MirrorUnavailableError",
    "AdmissionRejectedError",
    "InfrastructureError",
    "ConfigurationError",
    "StorageError",
    "BlobNotFoundError",
    "GitError",
    "GitUnavailableError",
    "GitCommandError",
    "RefNotFoundError",
]


class RiaError(Exception):
    """Base class for every error raised by this package.

    Args:
        message: Human-readable description. Must not contain secrets.
        context: Structured key/value detail suitable for structured logging.
    """

    #: Whether retrying the failed operation unchanged could plausibly succeed.
    is_retryable: bool = False

    def __init__(
        self, message: str, context: Optional[Mapping[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = dict(context or {})

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        if not self.context:
            return self.message
        rendered = " ".join(
            f"{key}={value!r}" for key, value in sorted(self.context.items())
        )
        return f"{self.message} ({rendered})"


# ---------------------------------------------------------------------------
# Domain errors — specification invariants
# ---------------------------------------------------------------------------


class DomainError(RiaError):
    """A specification invariant was violated. Never retryable."""


class InvalidMonikerError(DomainError):
    """A moniker string does not satisfy the grammar of Twin Spec section 3.1."""


class InvalidContentHashError(DomainError):
    """A content hash is not a well-formed ``sha256:<64 hex>`` value."""


class InvalidCommitShaError(DomainError):
    """A commit SHA is not a lowercase hexadecimal git object name."""


class InvalidPathError(DomainError):
    """A repository-relative path is absolute, escapes the root, or is empty."""


class IllegalStateTransitionError(DomainError):
    """A lifecycle transition is not permitted by the entity's transition table."""

    def __init__(self, entity: str, current: str, requested: str) -> None:
        super().__init__(
            f"{entity} cannot transition from {current} to {requested}",
            {"entity": entity, "current_state": current, "requested_state": requested},
        )
        self.entity = entity
        self.current = current
        self.requested = requested


class ImmutableFactViolationError(DomainError):
    """An attempt was made to rewrite facts that the specification declares immutable.

    Raised by the persistence adapters when a commit that has reached a terminal
    index state would have its factual fields changed. See Twin Spec section 3.2,
    entity ``Commit``: "Never updated after reaching ``queryable``".
    """


# ---------------------------------------------------------------------------
# Application errors — expected outcomes of use cases
# ---------------------------------------------------------------------------


class ApplicationError(RiaError):
    """A use case could not complete given the current state of the system."""


class RepositoryAlreadyExistsError(ApplicationError):
    """Registration was attempted for a moniker that is already registered."""


class RepositoryNotFoundError(ApplicationError):
    """The referenced repository is not registered."""


class CommitNotFoundError(ApplicationError):
    """The referenced commit is not recorded for the repository."""


class BranchNotFoundError(ApplicationError):
    """The referenced branch is not recorded for the repository."""


class JobNotFoundError(ApplicationError):
    """The referenced background job is not recorded."""


class MirrorUnavailableError(ApplicationError):
    """A repository's local mirror is absent or unusable.

    Distinct from :class:`GitError`: the mirror is our own cache, so its absence is a
    recoverable application state that acquisition resolves, not a git failure.
    """

    is_retryable = True


class AdmissionRejectedError(ApplicationError):
    """A repository exceeds a configured admission limit.

    SDD section 3 (L1 failure modes) requires that oversized repositories are
    rejected at admission rather than partially ingested.
    """


# ---------------------------------------------------------------------------
# Infrastructure errors — adapter failures
# ---------------------------------------------------------------------------


class InfrastructureError(RiaError):
    """An outbound adapter failed."""


class ConfigurationError(InfrastructureError):
    """Settings are absent, malformed, or mutually inconsistent."""


class StorageError(InfrastructureError):
    """A persistence adapter failed."""

    is_retryable = True


class BlobNotFoundError(InfrastructureError):
    """The requested content hash is absent from the content-addressable store."""


class GitError(InfrastructureError):
    """A git operation failed."""


class GitUnavailableError(GitError):
    """The configured git executable is missing or not runnable."""


class GitCommandError(GitError):
    """A git subprocess exited with a non-zero status.

    Args:
        argv: The command line that was executed, with no credentials embedded.
        exit_code: Process exit status.
        stderr: Captured standard error, truncated by the adapter.
    """

    is_retryable = True

    def __init__(self, argv: object, exit_code: int, stderr: str) -> None:
        super().__init__(
            f"git command failed with exit code {exit_code}",
            {"argv": argv, "exit_code": exit_code, "stderr": stderr},
        )
        self.exit_code = exit_code
        self.stderr = stderr


class RefNotFoundError(GitError):
    """A git ref could not be resolved to a commit."""
