"""Repository Manager use cases.

Implements the Repository Manager subsystem of SDD section 4: "Registration,
credentials, refs, clone lifecycle, admission limits", with the design note "Git
is the system of record; working copies are caches".

Scope at Milestone 1
--------------------
Registration, configuration, metadata and lifecycle. Cloning belongs to Milestone
2, so registration deliberately does not touch the network: it records intent to
index and leaves acquisition to the ingestion pipeline. Separating the two means a
registration cannot fail because a remote is briefly unreachable, and a
registration that has been accepted is durable regardless of network state.

Origin URL handling
-------------------
Credentials embedded in a URL are stripped before the entity is constructed. PRD
section 4.2 keeps facts free of secrets, and a credential persisted in a fact
would leak into every log line, error context and API response that echoes the
origin. Credentials belong to the control plane, not to the repository record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Sequence, Tuple
from urllib.parse import SplitResult, urlsplit, urlunsplit

from ria.domain.enums import RepositoryStatus
from ria.domain.errors import (
    ApplicationError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
)
from ria.domain.identity import Moniker, RepositoryId
from ria.domain.models.repository import (
    IndexPolicy,
    LanguageProfile,
    Repository,
    SizeMetrics,
)
from ria.observability.logging import get_logger, log_context
from ria.ports.clock import Clock
from ria.ports.metrics import MetricsSink
from ria.ports.unit_of_work import UnitOfWorkFactory

__all__ = ["RegisterRepositoryCommand", "RepositoryManager", "parse_origin_url"]

_LOGGER = get_logger(__name__)

#: Metric names emitted by this use case.
_METRIC_REGISTERED = "ria_repository_registered_total"
_METRIC_STATE_CHANGE = "ria_repository_state_change_total"
_METRIC_OPERATION_SECONDS = "ria_repository_operation_seconds"

#: ``scp``-style git remote, for example ``git@github.com:owner/name.git``. Not a
#: URL, so :func:`urllib.parse.urlsplit` cannot parse it and it is matched directly.
_SCP_REMOTE = re.compile(r"^(?:(?P<user>[^@/]+)@)?(?P<host>[^:/]+):(?P<path>.+)$")

#: Suffix stripped from a repository path component.
_GIT_SUFFIX = ".git"

#: URL schemes recognised as remote git endpoints.
_URL_SCHEMES = frozenset({"http", "https", "ssh", "git"})


def parse_origin_url(origin_url: str) -> Tuple[Moniker, str]:
    """Derive a repository moniker and a credential-free origin from a remote URL.

    Supports HTTPS, SSH and ``scp``-style remotes, and local filesystem paths. A
    local path yields the host ``local``, so a repository ingested from disk still
    has a well-formed moniker and can be joined against like any other.

    Args:
        origin_url: Remote URL or local path.

    Returns:
        The repository moniker and the origin URL with any credentials removed.

    Raises:
        ApplicationError: If the URL is empty or lacks an owner and name.
    """
    raw = (origin_url or "").strip()
    if not raw:
        raise ApplicationError("origin url must be non-empty")

    split = urlsplit(raw)

    if split.scheme in _URL_SCHEMES and split.netloc:
        host = split.hostname or "unknown"
        sanitised = urlunsplit(
            (split.scheme, _netloc_without_credentials(split), split.path, "", "")
        )
        return _moniker_from(host, split.path, raw), sanitised

    if split.scheme == "file":
        return _moniker_from("local", split.path, raw), raw

    # An scp-style remote is not a URL, so urlsplit misreads its host as a
    # scheme. Three conditions separate it from look-alikes:
    #   * a multi-character prefix before the colon, which excludes a Windows
    #     drive letter such as "C:/repos/acme/widgets";
    #   * no backslash separators, which also excludes Windows paths;
    #   * a path that does not begin with a slash. An unsupported URL such as
    #     "ftp://host/owner/name" otherwise matches with host "ftp" and path
    #     "//host/owner/name", producing the moniker repo:ftp:owner/name — a
    #     bogus host that would collide across forges and silently accept a
    #     scheme we do not support.
    scp = _SCP_REMOTE.match(raw)
    if (
        scp is not None
        and "\\" not in raw
        and len(scp.group("host")) > 1
        and not scp.group("path").startswith("/")
    ):
        host = scp.group("host")
        path = scp.group("path")
        user = scp.group("user")
        sanitised = f"{user}@{host}:{path}" if user else f"{host}:{path}"
        return _moniker_from(host, path, raw), sanitised

    if split.scheme == "" or len(split.scheme) == 1:
        # No scheme, or a single-letter scheme, which is a Windows drive letter.
        return _moniker_from("local", raw, raw), raw

    raise ApplicationError(
        "origin url scheme is not supported",
        {"origin_url": raw, "scheme": split.scheme},
    )


def _netloc_without_credentials(split: SplitResult) -> str:
    """Rebuild a network location with any userinfo removed.

    Args:
        split: Result of :func:`urllib.parse.urlsplit`.

    Returns:
        Host, with port preserved when present.
    """
    host = split.hostname or ""
    port = split.port
    return f"{host}:{port}" if port else host


def _moniker_from(host: str, path: str, original: str) -> Moniker:
    """Build a repository moniker from a host and path.

    Args:
        host: Forge hostname, or ``local`` for a filesystem path.
        path: Path component of the remote.
        original: Original input, used in the error context.

    Returns:
        A moniker of the form ``repo:host:owner/name``.

    Raises:
        ApplicationError: If the path does not yield an owner and a name.
    """
    normalised = path.replace("\\", "/").strip("/")
    if normalised.endswith(_GIT_SUFFIX):
        normalised = normalised[: -len(_GIT_SUFFIX)]
    segments = [segment for segment in normalised.split("/") if segment]
    if len(segments) < 2:
        raise ApplicationError(
            "origin url must contain an owner and a repository name",
            {"origin_url": original},
        )
    owner = segments[-2]
    name = segments[-1]
    return Moniker.for_repository(host=host, owner=owner, name=name)


@dataclass(frozen=True)
class RegisterRepositoryCommand:
    """Input to :meth:`RepositoryManager.register`.

    A command object rather than a long parameter list, so that adding an input in
    a later milestone does not change the method signature at every call site.

    Attributes:
        origin_url: Remote URL or local path of the repository.
        default_branch: Default branch name. When ``None``, a conventional default
            is recorded and corrected by branch discovery in Milestone 2. It is not
            probed here, because registration performs no network access.
        tenant_id: Owning tenant. When ``None``, the configured default is used.
        index_policy: Indexing configuration. When ``None``, the default policy
            applies.
    """

    origin_url: str
    default_branch: Optional[str] = None
    tenant_id: Optional[str] = None
    index_policy: Optional[IndexPolicy] = None


class RepositoryManager:
    """Registration, configuration and lifecycle of repositories.

    Args:
        unit_of_work_factory: Creates a transaction per operation.
        clock: Source of timestamps.
        metrics: Sink for operation counts and durations.
        default_tenant_id: Tenant assigned when a command does not specify one.
        provisional_default_branch: Branch name recorded at registration when the
            caller does not supply one.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        clock: Clock,
        metrics: MetricsSink,
        *,
        default_tenant_id: str = "default",
        provisional_default_branch: str = "main",
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._metrics = metrics
        self._default_tenant_id = default_tenant_id
        self._provisional_default_branch = provisional_default_branch

    # -- registration -----------------------------------------------------

    def register(self, command: RegisterRepositoryCommand) -> Repository:
        """Register a repository for indexing.

        Idempotency is deliberately *not* applied here: a second registration of
        the same moniker raises rather than returning the existing record. The two
        outcomes mean different things to a caller, and silently returning an
        existing repository would hide a configuration conflict in which two
        callers believe they own the same record with different policies.

        Args:
            command: Registration input.

        Returns:
            The registered repository.

        Raises:
            ApplicationError: If the origin URL cannot be parsed.
            RepositoryAlreadyExistsError: If the moniker is already registered.
            StorageError: If the write fails.
        """
        moniker, origin_url = parse_origin_url(command.origin_url)
        now = self._clock.now()
        repository = Repository(
            repository_id=RepositoryId.generate(),
            moniker=moniker,
            origin_url=origin_url,
            default_branch=command.default_branch or self._provisional_default_branch,
            tenant_id=command.tenant_id or self._default_tenant_id,
            registered_at=now,
            updated_at=now,
            status=RepositoryStatus.REGISTERED,
            index_policy=command.index_policy or IndexPolicy(),
        )

        with log_context(
            repository=str(moniker), repository_id=str(repository.repository_id)
        ):
            with self._metrics.timer(
                _METRIC_OPERATION_SECONDS, labels={"operation": "register"}
            ):
                with self._unit_of_work_factory() as unit_of_work:
                    existing = unit_of_work.repositories.get_by_moniker(moniker)
                    if existing is not None:
                        self._metrics.increment(
                            _METRIC_REGISTERED, labels={"outcome": "conflict"}
                        )
                        raise RepositoryAlreadyExistsError(
                            "repository is already registered",
                            {
                                "moniker": str(moniker),
                                "existing_repository_id": str(existing.repository_id),
                            },
                        )
                    unit_of_work.repositories.add(repository)
                    unit_of_work.commit()

            self._metrics.increment(
                _METRIC_REGISTERED, labels={"outcome": "registered"}
            )
            _LOGGER.info(
                "repository registered",
                extra={"origin_url": origin_url, "tenant_id": repository.tenant_id},
            )
        return repository

    # -- reads ------------------------------------------------------------

    def get(self, repository_id: RepositoryId) -> Repository:
        """Load a repository by identifier.

        Args:
            repository_id: Identifier to load.

        Returns:
            The repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
        """
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.repositories.get(repository_id)
        if repository is None:
            raise RepositoryNotFoundError(
                "repository is not registered", {"repository_id": str(repository_id)}
            )
        return repository

    def get_by_moniker(self, moniker: Moniker) -> Repository:
        """Load a repository by its logical identity.

        Args:
            moniker: Repository moniker.

        Returns:
            The repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
        """
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.repositories.get_by_moniker(moniker)
        if repository is None:
            raise RepositoryNotFoundError(
                "repository is not registered", {"moniker": str(moniker)}
            )
        return repository

    def find_by_moniker(self, moniker: Moniker) -> Optional[Repository]:
        """Load a repository by moniker, returning ``None`` when absent.

        Provided alongside :meth:`get_by_moniker` because existence checks are
        ordinary control flow and should not require exception handling.

        Args:
            moniker: Repository moniker.

        Returns:
            The repository, or ``None``.
        """
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repositories.get_by_moniker(moniker)

    def list(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Repository]:
        """List repositories in a deterministic order.

        Args:
            tenant_id: Restrict to one tenant.
            status: Restrict to one lifecycle state.
            limit: Maximum number of records.
            offset: Records to skip.

        Returns:
            Matching repositories, ordered by moniker ascending.
        """
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repositories.list(
                tenant_id=tenant_id, status=status, limit=limit, offset=offset
            )

    def count(
        self,
        *,
        tenant_id: Optional[str] = None,
        status: Optional[RepositoryStatus] = None,
    ) -> int:
        """Count repositories matching a filter.

        Args:
            tenant_id: Restrict to one tenant.
            status: Restrict to one lifecycle state.
        """
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.repositories.count(tenant_id=tenant_id, status=status)

    # -- configuration ----------------------------------------------------

    def update_index_policy(
        self, repository_id: RepositoryId, policy: IndexPolicy
    ) -> Repository:
        """Replace a repository's index policy.

        Args:
            repository_id: Repository to reconfigure.
            policy: New policy.

        Returns:
            The updated repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            StorageError: If the write fails.
        """
        return self._mutate(
            repository_id,
            lambda repository, now: repository.with_index_policy(policy, now=now),
            operation="update_index_policy",
        )

    def update_metadata(
        self,
        repository_id: RepositoryId,
        *,
        default_branch: Optional[str] = None,
        languages: Optional[Tuple[LanguageProfile, ...]] = None,
        frameworks: Optional[Tuple[str, ...]] = None,
        size_metrics: Optional[SizeMetrics] = None,
    ) -> Repository:
        """Record newly observed metadata.

        Arguments left as ``None`` are unchanged, which is distinct from clearing a
        value. Milestone 2's branch discovery corrects ``default_branch`` here, and
        Milestone 3's parser layer supplies ``languages``.

        Args:
            repository_id: Repository to update.
            default_branch: Newly observed default branch.
            languages: Newly measured language profiles.
            frameworks: Newly detected frameworks.
            size_metrics: Newly measured size.

        Returns:
            The updated repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            StorageError: If the write fails.
        """
        return self._mutate(
            repository_id,
            lambda repository, now: repository.with_metadata(
                now=now,
                default_branch=default_branch,
                languages=languages,
                frameworks=frameworks,
                size_metrics=size_metrics,
            ),
            operation="update_metadata",
        )

    # -- lifecycle --------------------------------------------------------

    def transition(
        self,
        repository_id: RepositoryId,
        status: RepositoryStatus,
        *,
        degraded_reason: Optional[str] = None,
    ) -> Repository:
        """Move a repository to a new lifecycle state.

        Args:
            repository_id: Repository to transition.
            status: Target state.
            degraded_reason: Required when the target state is ``DEGRADED``.

        Returns:
            The updated repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            IllegalStateTransitionError: If the transition is not permitted.
            StorageError: If the write fails.
        """
        repository = self._mutate(
            repository_id,
            lambda current, now: current.transition_to(
                status, now=now, degraded_reason=degraded_reason
            ),
            operation="transition",
        )
        self._metrics.increment(_METRIC_STATE_CHANGE, labels={"status": status.value})
        _LOGGER.info(
            "repository state changed",
            extra={
                "repository": repository.slug,
                "status": status.value,
                "degraded_reason": degraded_reason,
            },
        )
        return repository

    def record_successful_index(
        self, repository_id: RepositoryId, *, sha: str
    ) -> Repository:
        """Mark a repository active after a successful index build.

        Args:
            repository_id: Repository that was indexed.
            sha: Commit that was indexed.

        Returns:
            The updated repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            IllegalStateTransitionError: If the repository cannot become active.
            StorageError: If the write fails.
        """
        repository = self._mutate(
            repository_id,
            lambda current, now: current.with_successful_index(sha=sha, now=now),
            operation="record_successful_index",
        )
        self._metrics.increment(
            _METRIC_STATE_CHANGE, labels={"status": RepositoryStatus.ACTIVE.value}
        )
        return repository

    def archive(self, repository_id: RepositoryId) -> Repository:
        """Archive a repository, ending indexing without discarding facts.

        Args:
            repository_id: Repository to archive.

        Returns:
            The updated repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            StorageError: If the write fails.
        """
        return self.transition(repository_id, RepositoryStatus.ARCHIVED)

    def purge(self, repository_id: RepositoryId) -> bool:
        """Delete a repository and every fact owned by it.

        The terminal ``archived -> purged`` step. Irreversible, and permitted only
        from ``ARCHIVED``: requiring archival first means a purge is always a
        second, deliberate act rather than a single mistaken call.

        Args:
            repository_id: Repository to purge.

        Returns:
            ``True`` if a repository was removed.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
            ApplicationError: If the repository is not archived.
            StorageError: If the delete fails.
        """
        with log_context(repository_id=str(repository_id)):
            with self._unit_of_work_factory() as unit_of_work:
                repository = unit_of_work.repositories.get(repository_id)
                if repository is None:
                    raise RepositoryNotFoundError(
                        "repository is not registered",
                        {"repository_id": str(repository_id)},
                    )
                if repository.status is not RepositoryStatus.ARCHIVED:
                    raise ApplicationError(
                        "repository must be archived before it can be purged",
                        {
                            "repository_id": str(repository_id),
                            "status": repository.status.value,
                        },
                    )
                removed = unit_of_work.repositories.delete(repository_id)
                unit_of_work.commit()
            _LOGGER.warning("repository purged", extra={"repository": repository.slug})
        return removed

    # -- internals --------------------------------------------------------

    def _mutate(
        self,
        repository_id: RepositoryId,
        transform: Callable[[Repository, datetime], Repository],
        *,
        operation: str,
    ) -> Repository:
        """Load, transform and save a repository inside one transaction.

        Read-modify-write happens inside a single transaction so that two concurrent
        updates cannot each apply to a stale copy and silently lose one another's
        change. The transaction is ``BEGIN IMMEDIATE``, so the second writer waits
        rather than racing.

        Args:
            repository_id: Repository to mutate.
            transform: Callable taking the current entity and the current time, and
                returning the new entity.
            operation: Metric label naming the operation.

        Returns:
            The updated repository.

        Raises:
            RepositoryNotFoundError: If the repository is not registered.
        """
        with log_context(repository_id=str(repository_id)):
            with self._metrics.timer(
                _METRIC_OPERATION_SECONDS, labels={"operation": operation}
            ):
                with self._unit_of_work_factory() as unit_of_work:
                    current = unit_of_work.repositories.get(repository_id)
                    if current is None:
                        raise RepositoryNotFoundError(
                            "repository is not registered",
                            {"repository_id": str(repository_id)},
                        )
                    updated = transform(current, self._clock.now())
                    unit_of_work.repositories.save(updated)
                    unit_of_work.commit()
        return updated
