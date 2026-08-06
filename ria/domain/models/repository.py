"""Repository aggregate.

Implements Twin Spec section 3.2, entity ``Repository``, together with the index
policy that drives snapshot cadence and retention (Twin Spec section 6.3) and
the admission limits required by SDD section 3 (L1 failure modes).

The repository is the only entity in the structural core that is mutable, as the
specification states. Mutation is expressed as functional transformation:
methods return a new instance rather than modifying in place, so that a stale
reference can never be mistaken for current state. State changes go through
:meth:`Repository.transition_to`, which validates against the transition table.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import FrozenSet, Mapping, Optional, Tuple

from ria.domain.enums import (
    REPOSITORY_TRANSITIONS,
    BranchCadence,
    Facet,
    LanguageTier,
    RepositoryStatus,
    assert_transition,
)
from ria.domain.identity import Moniker, MonikerScheme, RepositoryId

__all__ = [
    "RetentionPolicy",
    "AdmissionLimits",
    "IndexPolicy",
    "LanguageProfile",
    "SizeMetrics",
    "Repository",
    "DEFAULT_INDEX_POLICY",
]

#: Sentinel retention value meaning "never evict".
RETAIN_FOREVER = -1


@dataclass(frozen=True)
class RetentionPolicy:
    """How long materialised artefacts are kept.

    Implements the retention rows of the snapshot cadence policy table in Twin
    Spec section 6.3. Lifetime events are absent from this policy on purpose:
    the specification requires that they be retained forever, so their retention
    is not configurable.

    Attributes:
        full_twin_days: Days to retain fully materialised twins.
        merge_commit_days: Days to retain twins for merge commits.
        release_days: Days to retain twins for tagged releases.
            :data:`RETAIN_FOREVER` by default, as the specification requires.
    """

    full_twin_days: int = 90
    merge_commit_days: int = 365
    release_days: int = RETAIN_FOREVER

    def __post_init__(self) -> None:
        for name, value in (
            ("full_twin_days", self.full_twin_days),
            ("merge_commit_days", self.merge_commit_days),
            ("release_days", self.release_days),
        ):
            if value != RETAIN_FOREVER and value <= 0:
                raise ValueError(
                    f"{name} must be positive or RETAIN_FOREVER, got {value}"
                )


@dataclass(frozen=True)
class AdmissionLimits:
    """Hard limits evaluated before a repository is accepted.

    SDD section 3 (L1, failure modes) requires that a repository exceeding a
    stated limit be "rejected at admission with a stated limit — never partially
    ingested silently". These fields are that stated limit.

    Attributes:
        max_files: Maximum number of files in a single commit tree.
        max_file_bytes: Maximum size of an individual file eligible for content
            addressing and parsing. Larger files are recorded but skipped.
        max_total_bytes: Maximum aggregate size of eligible files.
    """

    max_files: int = 500_000
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 20 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_files", self.max_files),
            ("max_file_bytes", self.max_file_bytes),
            ("max_total_bytes", self.max_total_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")


@dataclass(frozen=True)
class IndexPolicy:
    """Per-repository indexing configuration.

    Attributes:
        default_branch_cadence: Cadence applied to the default branch.
        feature_branch_cadence: Cadence applied to non-default branches.
        index_pull_requests: Whether to index the merge base and head of pull
            request branches, which is what makes the pull request diff of Twin
            Spec section 6.3 possible.
        index_tags: Whether tagged commits are always indexed.
        stale_branch_days: Branches with no commit newer than this are not
            indexed.
        facets: Facets to build for this repository. A facet absent here is
            reported as ``absent`` by the twin rather than silently omitted.
        retention: Retention policy for materialised artefacts.
        admission: Admission limits.
    """

    default_branch_cadence: BranchCadence = BranchCadence.EVERY_COMMIT
    feature_branch_cadence: BranchCadence = BranchCadence.HEAD_ONLY
    index_pull_requests: bool = True
    index_tags: bool = True
    stale_branch_days: int = 90
    facets: FrozenSet[Facet] = frozenset({Facet.STRUCTURE, Facet.HISTORY})
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)
    admission: AdmissionLimits = field(default_factory=AdmissionLimits)

    def __post_init__(self) -> None:
        if self.stale_branch_days <= 0:
            raise ValueError(
                f"stale_branch_days must be positive, got {self.stale_branch_days}"
            )
        if not self.facets:
            raise ValueError("at least one facet must be selected")
        if Facet.STRUCTURE not in self.facets:
            # Every other facet keys off structural identity (Twin Spec 3.1),
            # so a policy without STRUCTURE cannot produce a coherent twin.
            raise ValueError("the structure facet is mandatory")
        object.__setattr__(self, "facets", frozenset(self.facets))

    def cadence_for(self, *, is_default_branch: bool) -> BranchCadence:
        """Cadence that applies to a branch.

        Args:
            is_default_branch: Whether the branch is the repository default.
        """
        return (
            self.default_branch_cadence
            if is_default_branch
            else self.feature_branch_cadence
        )

    def includes(self, facet: Facet) -> bool:
        """Whether a facet is enabled for this repository.

        Args:
            facet: Facet to test.
        """
        return facet in self.facets


#: Policy applied when a repository is registered without an explicit one.
DEFAULT_INDEX_POLICY = IndexPolicy()


@dataclass(frozen=True)
class LanguageProfile:
    """Measured presence and declared capability for one language.

    Attributes:
        language: Canonical language name.
        loc: Lines of code attributed to the language.
        percentage: Share of the repository's eligible lines, in ``[0, 100]``.
        tier: Extraction tier available for the language.
        precision: Measured symbol resolution precision for this language, or
            ``None`` when unmeasured. PRD principle P8 forbids publishing a
            precision figure that has not been measured, so ``None`` is the only
            honest default.
    """

    language: str
    loc: int
    percentage: float
    tier: LanguageTier
    precision: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.language:
            raise ValueError("language must be non-empty")
        if self.loc < 0:
            raise ValueError(f"loc must be non-negative, got {self.loc}")
        if not 0.0 <= self.percentage <= 100.0:
            raise ValueError(
                f"percentage must be within [0, 100], got {self.percentage}"
            )
        if self.precision is not None and not 0.0 <= self.precision <= 1.0:
            raise ValueError(f"precision must be within [0, 1], got {self.precision}")


@dataclass(frozen=True)
class SizeMetrics:
    """Size of the repository at its default branch head.

    Every field is optional and defaults to ``None`` rather than zero. A newly
    registered repository has not been measured, and reporting zero symbols would
    be a fabricated fact, which PRD principle P11 and Twin Spec section 9
    prohibit.

    Attributes:
        files: Number of files in the tree.
        loc: Lines of code across eligible files.
        symbols: Number of resolved symbols. Populated from Milestone 4.
        edges: Number of relations. Populated from Milestone 5.
        measured_at: When the measurement was taken.
        measured_at_sha: Commit the measurement describes.
    """

    files: Optional[int] = None
    loc: Optional[int] = None
    symbols: Optional[int] = None
    edges: Optional[int] = None
    measured_at: Optional[datetime] = None
    measured_at_sha: Optional[str] = None

    def __post_init__(self) -> None:
        for name in ("files", "loc", "symbols", "edges"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def is_measured(self) -> bool:
        """Whether any measurement has been recorded."""
        return self.measured_at is not None


@dataclass(frozen=True)
class Repository:
    """A registered repository.

    Attributes:
        repository_id: Internal stable identifier.
        moniker: Logical identity, of the form ``repo:host:owner/name``.
        origin_url: Upstream clone URL. Never contains embedded credentials;
            credentials are held by the control plane, not the entity.
        default_branch: Name of the default branch as reported by the origin.
        tenant_id: Isolation boundary. Present from Milestone 1 because SDD
            section 2.2 requires that tenancy not be retrofitted.
        status: Lifecycle state.
        index_policy: Indexing configuration.
        languages: Measured language profiles, empty until first measurement.
        frameworks: Detected framework identifiers, which drive entry-point
            descriptors in Milestone 4. Empty until detection runs.
        size_metrics: Measured size, unmeasured by default.
        registered_at: When registration occurred.
        updated_at: When the record last changed.
        last_indexed_at: When an index build last completed successfully.
        last_indexed_sha: Commit of the last successful index build.
        degraded_reason: Why the repository is degraded. Mandatory whenever
            status is ``DEGRADED`` so that degradation is never silent
            (PRD principle P11).
    """

    repository_id: RepositoryId
    moniker: Moniker
    origin_url: str
    default_branch: str
    tenant_id: str
    registered_at: datetime
    updated_at: datetime
    status: RepositoryStatus = RepositoryStatus.REGISTERED
    index_policy: IndexPolicy = field(default_factory=IndexPolicy)
    languages: Tuple[LanguageProfile, ...] = ()
    frameworks: Tuple[str, ...] = ()
    size_metrics: SizeMetrics = field(default_factory=SizeMetrics)
    last_indexed_at: Optional[datetime] = None
    last_indexed_sha: Optional[str] = None
    degraded_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.moniker.scheme != MonikerScheme.REPOSITORY:
            raise ValueError(
                f"repository moniker must use the {MonikerScheme.REPOSITORY!r} scheme, "
                f"got {self.moniker.scheme!r}"
            )
        if not self.origin_url.strip():
            raise ValueError("origin_url must be non-empty")
        if not self.default_branch.strip():
            raise ValueError("default_branch must be non-empty")
        if not self.tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if self.status is RepositoryStatus.DEGRADED and not self.degraded_reason:
            raise ValueError("degraded_reason is mandatory when status is DEGRADED")
        if self.status is not RepositoryStatus.DEGRADED and self.degraded_reason:
            raise ValueError("degraded_reason must be absent unless status is DEGRADED")
        object.__setattr__(self, "languages", tuple(self.languages))
        object.__setattr__(self, "frameworks", tuple(self.frameworks))

    # -- identity ---------------------------------------------------------

    @property
    def host(self) -> str:
        """Forge hostname component of the moniker."""
        return self.moniker.package

    @property
    def owner(self) -> str:
        """Owner component of the moniker."""
        return self.moniker.descriptor.split("/", 1)[0]

    @property
    def name(self) -> str:
        """Repository name component of the moniker."""
        parts = self.moniker.descriptor.split("/", 1)
        return parts[1] if len(parts) == 2 else parts[0]

    @property
    def slug(self) -> str:
        """``owner/name`` form, for logs and display."""
        return self.moniker.descriptor

    # -- transitions ------------------------------------------------------

    def transition_to(
        self,
        status: RepositoryStatus,
        *,
        now: datetime,
        degraded_reason: Optional[str] = None,
    ) -> "Repository":
        """Return a copy of this repository in a new lifecycle state.

        Args:
            status: Target state.
            now: Timestamp to record as ``updated_at``.
            degraded_reason: Required when ``status`` is
                :attr:`~ria.domain.enums.RepositoryStatus.DEGRADED`, forbidden
                otherwise.

        Returns:
            A new :class:`Repository` in the requested state.

        Raises:
            IllegalStateTransitionError: If the transition is not permitted.
            ValueError: If the degraded reason is missing or unexpectedly present.
        """
        assert_transition("Repository", self.status, status, REPOSITORY_TRANSITIONS)
        reason = degraded_reason if status is RepositoryStatus.DEGRADED else None
        return replace(self, status=status, degraded_reason=reason, updated_at=now)

    def with_index_policy(self, policy: IndexPolicy, *, now: datetime) -> "Repository":
        """Return a copy with a replaced index policy.

        Args:
            policy: New policy.
            now: Timestamp to record as ``updated_at``.
        """
        return replace(self, index_policy=policy, updated_at=now)

    def with_metadata(
        self,
        *,
        now: datetime,
        default_branch: Optional[str] = None,
        languages: Optional[Tuple[LanguageProfile, ...]] = None,
        frameworks: Optional[Tuple[str, ...]] = None,
        size_metrics: Optional[SizeMetrics] = None,
    ) -> "Repository":
        """Return a copy with refreshed observed metadata.

        Only the arguments supplied are changed; ``None`` means "leave as is",
        which is distinct from clearing a value.

        Args:
            now: Timestamp to record as ``updated_at``.
            default_branch: Newly observed default branch.
            languages: Newly measured language profiles.
            frameworks: Newly detected frameworks.
            size_metrics: Newly measured size.
        """
        return replace(
            self,
            default_branch=default_branch
            if default_branch is not None
            else self.default_branch,
            languages=tuple(languages) if languages is not None else self.languages,
            frameworks=tuple(frameworks) if frameworks is not None else self.frameworks,
            size_metrics=size_metrics
            if size_metrics is not None
            else self.size_metrics,
            updated_at=now,
        )

    def with_successful_index(self, *, sha: str, now: datetime) -> "Repository":
        """Return a copy marked active after a successful index build.

        Args:
            sha: Commit that was indexed.
            now: Timestamp of completion.

        Raises:
            IllegalStateTransitionError: If the repository is not in a state from
                which it may become active.
        """
        assert_transition(
            "Repository", self.status, RepositoryStatus.ACTIVE, REPOSITORY_TRANSITIONS
        )
        return replace(
            self,
            status=RepositoryStatus.ACTIVE,
            degraded_reason=None,
            last_indexed_at=now,
            last_indexed_sha=sha,
            updated_at=now,
        )

    def language_by_name(self) -> Mapping[str, LanguageProfile]:
        """Index the language profiles by canonical language name."""
        return {profile.language: profile for profile in self.languages}
