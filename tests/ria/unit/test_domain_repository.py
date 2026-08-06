"""Tests for the repository aggregate and its configuration value objects."""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.enums import BranchCadence, Facet, LanguageTier, RepositoryStatus
from ria.domain.errors import IllegalStateTransitionError
from ria.domain.identity import Moniker, RepositoryId
from ria.domain.models.repository import (
    RETAIN_FOREVER,
    AdmissionLimits,
    IndexPolicy,
    LanguageProfile,
    Repository,
    RetentionPolicy,
    SizeMetrics,
)
from tests.ria.conftest import utc

NOW = utc(2026, 1, 1, 12)
LATER = utc(2026, 1, 2, 12)


def make_repository(**overrides) -> Repository:
    """Build a repository with sensible defaults for a test.

    Args:
        **overrides: Fields to replace.

    Returns:
        A valid repository in the ``REGISTERED`` state unless overridden.
    """
    defaults = dict(
        repository_id=RepositoryId.generate(),
        moniker=Moniker.for_repository(host="github.com", owner="acme", name="widgets"),
        origin_url="https://github.com/acme/widgets.git",
        default_branch="main",
        tenant_id="tenant-a",
        registered_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return Repository(**defaults)


class TestConstruction:
    """Invariants enforced when a repository is constructed."""

    def test_accepts_a_well_formed_repository(self) -> None:
        """A repository with a valid moniker and origin is constructible."""
        repository = make_repository()
        assert repository.status is RepositoryStatus.REGISTERED
        assert repository.slug == "acme/widgets"

    def test_rejects_a_non_repository_moniker(self) -> None:
        """The moniker must use the ``repo`` scheme.

        Accepting a file moniker here would produce an entity whose identity claims
        to be a file, breaking every join that assumes the scheme.
        """
        with pytest.raises(ValueError, match="scheme"):
            make_repository(moniker=Moniker.for_file("src/a.py"))

    @pytest.mark.parametrize("field", ["origin_url", "default_branch", "tenant_id"])
    def test_rejects_blank_required_text(self, field: str) -> None:
        """Blank required text is rejected rather than stored."""
        with pytest.raises(ValueError):
            make_repository(**{field: "   "})

    def test_requires_a_reason_when_degraded(self) -> None:
        """A degraded repository must say why.

        PRD principle P11 forbids silent degradation: a degraded state with no
        stated cause is indistinguishable from a bug in our own pipeline.
        """
        with pytest.raises(ValueError, match="degraded_reason is mandatory"):
            make_repository(status=RepositoryStatus.DEGRADED)

    def test_forbids_a_reason_when_not_degraded(self) -> None:
        """A stale degradation reason on a healthy repository is rejected."""
        with pytest.raises(ValueError, match="must be absent"):
            make_repository(status=RepositoryStatus.ACTIVE, degraded_reason="left over")

    def test_is_immutable(self) -> None:
        """Fields cannot be assigned; change is expressed by transformation."""
        repository = make_repository()
        with pytest.raises(dataclasses.FrozenInstanceError):
            repository.status = RepositoryStatus.ACTIVE  # type: ignore[misc]

    def test_normalises_collections_to_tuples(self) -> None:
        """Sequences are stored as tuples so a caller's list cannot mutate the entity."""
        languages = [
            LanguageProfile(
                language="python", loc=10, percentage=100.0, tier=LanguageTier.NONE
            )
        ]
        repository = make_repository(languages=languages, frameworks=["fastapi"])
        languages.clear()
        assert len(repository.languages) == 1
        assert isinstance(repository.frameworks, tuple)


class TestIdentityAccessors:
    """Components derived from the moniker."""

    def test_splits_host_owner_and_name(self) -> None:
        """Host, owner and name are read from the moniker, not stored separately."""
        repository = make_repository()
        assert (repository.host, repository.owner, repository.name) == (
            "github.com",
            "acme",
            "widgets",
        )

    def test_handles_nested_owner_paths(self) -> None:
        """A group-nested path keeps everything after the first segment as the name."""
        repository = make_repository(
            moniker=Moniker(
                scheme="repo", package="gitlab.com", descriptor="group/sub/proj"
            )
        )
        assert repository.owner == "group"
        assert repository.name == "sub/proj"


class TestTransitions:
    """Lifecycle transformations."""

    def test_transition_records_the_new_state_and_time(self) -> None:
        """A transition produces a new entity with a refreshed timestamp."""
        repository = make_repository()
        moved = repository.transition_to(RepositoryStatus.INDEXING, now=LATER)
        assert moved.status is RepositoryStatus.INDEXING
        assert moved.updated_at == LATER
        assert repository.status is RepositoryStatus.REGISTERED

    def test_transition_rejects_an_illegal_target(self) -> None:
        """An undeclared transition raises rather than being applied."""
        archived = make_repository(status=RepositoryStatus.ARCHIVED)
        with pytest.raises(IllegalStateTransitionError):
            archived.transition_to(RepositoryStatus.ACTIVE, now=LATER)

    def test_transition_to_degraded_carries_the_reason(self) -> None:
        """Degrading records the supplied cause."""
        repository = make_repository(status=RepositoryStatus.ACTIVE)
        degraded = repository.transition_to(
            RepositoryStatus.DEGRADED, now=LATER, degraded_reason="clone failed"
        )
        assert degraded.degraded_reason == "clone failed"

    def test_leaving_degraded_clears_the_reason(self) -> None:
        """Recovery discards the reason so it cannot linger as a false signal."""
        degraded = make_repository(
            status=RepositoryStatus.DEGRADED, degraded_reason="clone failed"
        )
        recovered = degraded.transition_to(RepositoryStatus.ACTIVE, now=LATER)
        assert recovered.degraded_reason is None

    def test_degraded_reason_is_ignored_for_other_targets(self) -> None:
        """A reason supplied for a non-degraded target is dropped, not stored."""
        repository = make_repository()
        moved = repository.transition_to(
            RepositoryStatus.INDEXING, now=LATER, degraded_reason="irrelevant"
        )
        assert moved.degraded_reason is None

    def test_successful_index_records_the_commit(self) -> None:
        """A completed build marks the repository active and records what it indexed."""
        repository = make_repository(status=RepositoryStatus.INDEXING)
        indexed = repository.with_successful_index(sha="a" * 40, now=LATER)
        assert indexed.status is RepositoryStatus.ACTIVE
        assert indexed.last_indexed_sha == "a" * 40
        assert indexed.last_indexed_at == LATER

    def test_successful_index_clears_degradation(self) -> None:
        """A successful build is evidence that a prior degradation is resolved."""
        degraded = make_repository(
            status=RepositoryStatus.DEGRADED, degraded_reason="clone failed"
        )
        indexed = degraded.with_successful_index(sha="a" * 40, now=LATER)
        assert indexed.degraded_reason is None

    def test_successful_index_is_rejected_from_a_terminal_state(self) -> None:
        """An archived repository cannot be revived by an index build."""
        archived = make_repository(status=RepositoryStatus.ARCHIVED)
        with pytest.raises(IllegalStateTransitionError):
            archived.with_successful_index(sha="a" * 40, now=LATER)


class TestMetadataUpdates:
    """Partial metadata replacement."""

    def test_updates_only_the_supplied_fields(self) -> None:
        """``None`` means unchanged, which is distinct from clearing a value."""
        repository = make_repository(frameworks=("fastapi",))
        updated = repository.with_metadata(now=LATER, default_branch="trunk")
        assert updated.default_branch == "trunk"
        assert updated.frameworks == ("fastapi",)
        assert updated.updated_at == LATER

    def test_replaces_language_profiles_wholesale(self) -> None:
        """Language measurement replaces the previous observation rather than merging."""
        repository = make_repository()
        profile = LanguageProfile(
            language="python", loc=1200, percentage=80.0, tier=LanguageTier.NONE
        )
        updated = repository.with_metadata(now=LATER, languages=(profile,))
        assert updated.language_by_name()["python"].loc == 1200

    def test_policy_replacement_refreshes_the_timestamp(self) -> None:
        """Reconfiguration is a change and is timestamped as one."""
        repository = make_repository()
        policy = IndexPolicy(feature_branch_cadence=BranchCadence.NEVER)
        updated = repository.with_index_policy(policy, now=LATER)
        assert updated.index_policy.feature_branch_cadence is BranchCadence.NEVER
        assert updated.updated_at == LATER


class TestIndexPolicy:
    """Validation and behaviour of :class:`~ria.domain.models.repository.IndexPolicy`."""

    def test_defaults_match_the_specification(self) -> None:
        """Defaults implement the snapshot cadence table of Twin Spec section 6.3."""
        policy = IndexPolicy()
        assert policy.default_branch_cadence is BranchCadence.EVERY_COMMIT
        assert policy.feature_branch_cadence is BranchCadence.HEAD_ONLY
        assert policy.index_pull_requests is True

    def test_structure_facet_is_mandatory(self) -> None:
        """Every other facet keys off structural identity, so it cannot be omitted.

        Twin Spec section 3.1 makes structural monikers the shared identity space;
        a policy without structure could not produce a coherent twin.
        """
        with pytest.raises(ValueError, match="structure facet is mandatory"):
            IndexPolicy(facets=frozenset({Facet.HISTORY}))

    def test_rejects_an_empty_facet_set(self) -> None:
        """A repository must build at least one facet."""
        with pytest.raises(ValueError):
            IndexPolicy(facets=frozenset())

    def test_rejects_non_positive_staleness_window(self) -> None:
        """A zero window would mark every branch stale immediately."""
        with pytest.raises(ValueError):
            IndexPolicy(stale_branch_days=0)

    def test_cadence_selection_depends_on_default_branch(self) -> None:
        """Cadence is resolved from whether the branch is the default."""
        policy = IndexPolicy()
        assert policy.cadence_for(is_default_branch=True) is BranchCadence.EVERY_COMMIT
        assert policy.cadence_for(is_default_branch=False) is BranchCadence.HEAD_ONLY

    def test_facet_membership(self) -> None:
        """Facet selection is queryable so a builder can skip absent facets."""
        policy = IndexPolicy()
        assert policy.includes(Facet.STRUCTURE)
        assert not policy.includes(Facet.RUNTIME)

    def test_facets_are_frozen(self) -> None:
        """A caller's mutable set cannot alter the policy after construction."""
        supplied = {Facet.STRUCTURE, Facet.HISTORY}
        policy = IndexPolicy(facets=supplied)
        supplied.clear()
        assert len(policy.facets) == 2


class TestRetentionPolicy:
    """Validation of retention windows."""

    def test_release_retention_is_forever_by_default(self) -> None:
        """Twin Spec section 6.3 requires releases to be retained permanently."""
        assert RetentionPolicy().release_days == RETAIN_FOREVER

    @pytest.mark.parametrize(
        "field", ["full_twin_days", "merge_commit_days", "release_days"]
    )
    def test_rejects_non_positive_windows(self, field: str) -> None:
        """Zero or negative windows are rejected unless they are the forever sentinel."""
        with pytest.raises(ValueError):
            RetentionPolicy(**{field: 0})

    def test_accepts_the_forever_sentinel_for_any_window(self) -> None:
        """Any artefact class may be retained permanently."""
        policy = RetentionPolicy(full_twin_days=RETAIN_FOREVER)
        assert policy.full_twin_days == RETAIN_FOREVER


class TestAdmissionLimits:
    """Validation of admission limits."""

    @pytest.mark.parametrize(
        "field", ["max_files", "max_file_bytes", "max_total_bytes"]
    )
    def test_rejects_non_positive_limits(self, field: str) -> None:
        """A non-positive limit would reject every repository."""
        with pytest.raises(ValueError):
            AdmissionLimits(**{field: 0})

    def test_defaults_are_stated_rather_than_implied(self) -> None:
        """SDD section 3 requires a stated limit so rejection can cite it."""
        limits = AdmissionLimits()
        assert limits.max_files > 0
        assert limits.max_file_bytes > 0


class TestSizeMetrics:
    """Unmeasured-versus-zero semantics."""

    def test_defaults_are_unmeasured_not_zero(self) -> None:
        """A newly registered repository has no measurements.

        Reporting zero symbols would be a fabricated fact, which Twin Spec section 9
        prohibits, so every field defaults to ``None``.
        """
        metrics = SizeMetrics()
        assert metrics.files is None
        assert metrics.symbols is None
        assert metrics.is_measured is False

    def test_is_measured_becomes_true_once_timestamped(self) -> None:
        """A measurement is identified by its timestamp, not by non-zero values."""
        metrics = SizeMetrics(files=0, loc=0, measured_at=NOW, measured_at_sha="a" * 40)
        assert metrics.is_measured is True

    @pytest.mark.parametrize("field", ["files", "loc", "symbols", "edges"])
    def test_rejects_negative_counts(self, field: str) -> None:
        """Negative counts are impossible and are rejected."""
        with pytest.raises(ValueError):
            SizeMetrics(**{field: -1})


class TestLanguageProfile:
    """Validation of measured language presence."""

    def test_precision_is_unmeasured_by_default(self) -> None:
        """PRD principle P8 forbids publishing an unmeasured precision figure."""
        profile = LanguageProfile(
            language="python", loc=10, percentage=5.0, tier=LanguageTier.NONE
        )
        assert profile.precision is None

    @pytest.mark.parametrize("percentage", [-0.1, 100.1])
    def test_rejects_out_of_range_percentage(self, percentage: float) -> None:
        """A share outside ``[0, 100]`` is rejected."""
        with pytest.raises(ValueError):
            LanguageProfile(
                language="python",
                loc=1,
                percentage=percentage,
                tier=LanguageTier.NONE,
            )

    @pytest.mark.parametrize("precision", [-0.01, 1.01])
    def test_rejects_out_of_range_precision(self, precision: float) -> None:
        """Precision is a proportion and must lie within ``[0, 1]``."""
        with pytest.raises(ValueError):
            LanguageProfile(
                language="python",
                loc=1,
                percentage=1.0,
                tier=LanguageTier.NONE,
                precision=precision,
            )

    def test_rejects_blank_language(self) -> None:
        """A profile must name its language."""
        with pytest.raises(ValueError):
            LanguageProfile(language="", loc=1, percentage=1.0, tier=LanguageTier.NONE)

    def test_rejects_negative_loc(self) -> None:
        """Negative lines of code are impossible."""
        with pytest.raises(ValueError):
            LanguageProfile(
                language="python", loc=-1, percentage=1.0, tier=LanguageTier.NONE
            )
