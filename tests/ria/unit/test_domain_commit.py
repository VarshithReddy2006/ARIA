"""Tests for the commit entity, its coverage report and its fact immutability.

The fingerprint tests are the most important in this module. Twin Spec section 3.2
states that a commit is "never updated after reaching ``queryable``", and the
fingerprint is the mechanism that turns that sentence into an enforced invariant.
"""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.enums import CommitIndexState
from ria.domain.errors import IllegalStateTransitionError, ImmutableFactViolationError
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.commit import (
    ChangeStats,
    Commit,
    CommitCoverage,
    CommitRef,
    LanguageCoverage,
)
from ria.domain.models.person import PersonRef
from tests.ria.conftest import utc

SHA = "a" * 40
PARENT = "b" * 40
OTHER = "c" * 40
AUTHORED = utc(2026, 1, 1, 9)
COMMITTED = utc(2026, 1, 1, 10)
INDEXED = utc(2026, 1, 1, 11)


def make_commit(**overrides) -> Commit:
    """Build a commit with sensible defaults for a test.

    Args:
        **overrides: Fields to replace.

    Returns:
        A valid commit in the ``DISCOVERED`` state unless overridden.
    """
    defaults = dict(
        repository_id=RepositoryId.generate(),
        sha=CommitSha(SHA),
        parents=(CommitSha(PARENT),),
        author=PersonRef(name="Ada Lovelace", email="ada@example.com"),
        committer=PersonRef(name="Ada Lovelace", email="ada@example.com"),
        authored_at=AUTHORED,
        committed_at=COMMITTED,
        message="fix: correct the off-by-one\n\nDetail.",
        tree_hash="t" * 40,
    )
    defaults.update(overrides)
    return Commit(**defaults)


class TestConstruction:
    """Invariants enforced when a commit is constructed."""

    def test_accepts_a_well_formed_commit(self) -> None:
        """A commit with a tree hash and consistent state is constructible."""
        commit = make_commit()
        assert commit.index_state is CommitIndexState.DISCOVERED
        assert commit.coverage is None

    def test_rejects_a_missing_tree_hash(self) -> None:
        """A commit without a tree describes no content."""
        with pytest.raises(ValueError, match="tree_hash"):
            make_commit(tree_hash="")

    def test_requires_a_reason_when_failed(self) -> None:
        """A failed build must state why, so a coverage gap always has a cause."""
        with pytest.raises(ValueError, match="failure_reason is mandatory"):
            make_commit(index_state=CommitIndexState.FAILED)

    def test_forbids_a_reason_when_not_failed(self) -> None:
        """A stale failure reason on a healthy commit is rejected."""
        with pytest.raises(ValueError, match="must be absent"):
            make_commit(
                index_state=CommitIndexState.PENDING, failure_reason="left over"
            )

    def test_is_immutable(self) -> None:
        """Fields cannot be assigned; change is expressed by transformation."""
        commit = make_commit()
        with pytest.raises(dataclasses.FrozenInstanceError):
            commit.message = "rewritten"  # type: ignore[misc]

    def test_parents_are_normalised_to_a_tuple(self) -> None:
        """A caller's list cannot mutate the entity's parents afterwards."""
        parents = [CommitSha(PARENT)]
        commit = make_commit(parents=parents)
        parents.clear()
        assert len(commit.parents) == 1


class TestAccessors:
    """Derived properties of a commit."""

    def test_identifies_a_merge(self) -> None:
        """More than one parent means the commit is a merge."""
        merge = make_commit(parents=(CommitSha(PARENT), CommitSha(OTHER)))
        assert merge.is_merge is True
        assert make_commit().is_merge is False

    def test_identifies_a_root_commit(self) -> None:
        """A commit with no parents is the start of history."""
        root = make_commit(parents=())
        assert root.is_root is True
        assert root.first_parent is None

    def test_first_parent_defines_the_mainline(self) -> None:
        """Diff and churn are computed against the first parent."""
        merge = make_commit(parents=(CommitSha(PARENT), CommitSha(OTHER)))
        assert merge.first_parent == CommitSha(PARENT)

    def test_subject_is_the_first_message_line(self) -> None:
        """The subject excludes the body, which may be arbitrarily long."""
        assert make_commit().subject == "fix: correct the off-by-one"

    def test_commit_id_combines_repository_and_sha(self) -> None:
        """The composite key is derived, never stored twice."""
        commit = make_commit()
        assert commit.commit_id.repository_id == commit.repository_id
        assert commit.commit_id.sha == commit.sha


class TestFactImmutability:
    """The fingerprint mechanism protecting recorded history."""

    def test_fingerprint_is_stable_across_identical_facts(self) -> None:
        """Two entities describing the same commit agree on their fingerprint.

        This is what lets the adapter re-observe a commit from git and confirm it
        matches the record without storing every field twice.
        """
        repository_id = RepositoryId.generate()
        first = make_commit(repository_id=repository_id)
        second = make_commit(repository_id=repository_id)
        assert first.facts_fingerprint() == second.facts_fingerprint()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"message": "different"},
            {"tree_hash": "z" * 40},
            {"parents": ()},
            {"authored_at": utc(2026, 2, 1)},
            {"committed_at": utc(2026, 2, 1)},
            {"author": PersonRef(name="Grace Hopper", email="grace@example.com")},
            {"committer": PersonRef(name="Grace Hopper", email="grace@example.com")},
        ],
    )
    def test_fingerprint_changes_when_any_fact_changes(self, overrides: dict) -> None:
        """Every field declared factual participates in the digest."""
        repository_id = RepositoryId.generate()
        baseline = make_commit(repository_id=repository_id)
        altered = make_commit(repository_id=repository_id, **overrides)
        assert altered.facts_fingerprint() != baseline.facts_fingerprint()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"index_state": CommitIndexState.PENDING},
            {"change_stats": ChangeStats(files_changed=4, insertions=10, deletions=2)},
        ],
    )
    def test_fingerprint_ignores_processing_state(self, overrides: dict) -> None:
        """Our processing of a commit is not a fact about the commit.

        Index state and change statistics may be recomputed, so including them
        would make every legitimate update look like a history rewrite.
        """
        repository_id = RepositoryId.generate()
        baseline = make_commit(repository_id=repository_id)
        altered = make_commit(repository_id=repository_id, **overrides)
        assert altered.facts_fingerprint() == baseline.facts_fingerprint()

    def test_fingerprint_distinguishes_repositories(self) -> None:
        """The same commit in two repositories has two fingerprints.

        Forks share object names, so omitting the repository would let one fork's
        record satisfy another's immutability check.
        """
        first = make_commit(repository_id=RepositoryId.generate())
        second = make_commit(repository_id=RepositoryId.generate())
        assert first.facts_fingerprint() != second.facts_fingerprint()

    def test_assert_facts_match_accepts_the_recorded_digest(self) -> None:
        """Verification passes when the facts are unchanged."""
        commit = make_commit()
        commit.assert_facts_match(commit.facts_fingerprint())

    def test_assert_facts_match_rejects_a_rewrite_with_both_digests(self) -> None:
        """A mismatch raises and reports the expected and actual digests."""
        repository_id = RepositoryId.generate()
        recorded = make_commit(repository_id=repository_id).facts_fingerprint()
        rewritten = make_commit(repository_id=repository_id, message="rewritten")
        with pytest.raises(ImmutableFactViolationError) as caught:
            rewritten.assert_facts_match(recorded)
        assert caught.value.context["expected_fingerprint"] == recorded
        assert (
            caught.value.context["actual_fingerprint"] == rewritten.facts_fingerprint()
        )

    def test_field_separators_prevent_digest_collisions(self) -> None:
        """Concatenating adjacent fields cannot produce the same digest.

        Without delimiters, moving a character between two adjacent fields would
        leave the digest unchanged, and a history rewrite would pass verification.
        """
        repository_id = RepositoryId.generate()
        first = make_commit(
            repository_id=repository_id, message="ab", tree_hash="c" * 40
        )
        second = make_commit(
            repository_id=repository_id, message="a", tree_hash="bc" + "c" * 38
        )
        assert first.facts_fingerprint() != second.facts_fingerprint()


class TestTransitions:
    """Index lifecycle transformations."""

    def test_advances_one_step(self) -> None:
        """A declared transition produces a new entity in the requested state."""
        commit = make_commit()
        pending = commit.transition_to(CommitIndexState.PENDING)
        assert pending.index_state is CommitIndexState.PENDING
        assert commit.index_state is CommitIndexState.DISCOVERED

    def test_rejects_skipping_to_queryable(self) -> None:
        """Visibility is reachable only from ``INDEXING``."""
        with pytest.raises(IllegalStateTransitionError):
            make_commit().transition_to(CommitIndexState.QUERYABLE, now=INDEXED)

    def test_queryable_requires_a_timestamp(self) -> None:
        """Becoming visible records when the build completed."""
        indexing = make_commit(index_state=CommitIndexState.INDEXING)
        with pytest.raises(ValueError, match="now is required"):
            indexing.transition_to(CommitIndexState.QUERYABLE)

    def test_queryable_records_coverage_and_time(self) -> None:
        """The completed build's coverage is attached at the visibility boundary."""
        indexing = make_commit(index_state=CommitIndexState.INDEXING)
        coverage = CommitCoverage(files_total=10, files_eligible=8, files_parsed=8)
        queryable = indexing.transition_to(
            CommitIndexState.QUERYABLE, now=INDEXED, coverage=coverage
        )
        assert queryable.indexed_at == INDEXED
        assert queryable.coverage is coverage

    def test_coverage_is_rejected_on_other_transitions(self) -> None:
        """Coverage that does not describe a completed build is not a statement.

        Permitting it would let a partially built commit advertise coverage, which
        is precisely the half-built-index answer SDD section 5.1 forbids.
        """
        commit = make_commit()
        coverage = CommitCoverage(files_total=1, files_eligible=1, files_parsed=1)
        with pytest.raises(ValueError, match="coverage may only be recorded"):
            commit.transition_to(CommitIndexState.PENDING, coverage=coverage)

    def test_failure_requires_a_reason(self) -> None:
        """A failure must state its cause."""
        pending = make_commit(index_state=CommitIndexState.PENDING)
        with pytest.raises(ValueError, match="failure_reason is required"):
            pending.transition_to(CommitIndexState.FAILED)

    def test_failure_records_the_reason(self) -> None:
        """The stated cause is retained on the entity."""
        pending = make_commit(index_state=CommitIndexState.PENDING)
        failed = pending.transition_to(
            CommitIndexState.FAILED, failure_reason="parser crashed"
        )
        assert failed.failure_reason == "parser crashed"

    def test_retry_clears_the_failure_reason(self) -> None:
        """Re-queueing a failed commit discards the stale cause."""
        failed = make_commit(
            index_state=CommitIndexState.FAILED, failure_reason="parser crashed"
        )
        retried = failed.transition_to(CommitIndexState.PENDING)
        assert retried.failure_reason is None

    def test_orphaning_preserves_every_fact(self) -> None:
        """Orphaning changes only the index state.

        Twin Spec section 3.2 requires this: deleting an orphaned commit's facts
        would rewrite our own history and invalidate answers already given.
        """
        queryable = make_commit(
            index_state=CommitIndexState.QUERYABLE, indexed_at=INDEXED
        )
        orphaned = queryable.mark_orphaned()
        assert orphaned.index_state is CommitIndexState.ORPHANED
        assert orphaned.facts_fingerprint() == queryable.facts_fingerprint()
        assert orphaned.message == queryable.message
        assert orphaned.indexed_at == INDEXED

    def test_a_self_transition_is_permitted_for_idempotency(self) -> None:
        """A retried job may assert its target state without knowing the current one."""
        pending = make_commit(index_state=CommitIndexState.PENDING)
        assert pending.transition_to(CommitIndexState.PENDING).index_state is (
            CommitIndexState.PENDING
        )


class TestChangeStats:
    """Validation and derivation of change statistics."""

    def test_churn_is_the_sum_of_both_directions(self) -> None:
        """Churn counts lines touched, not the net change."""
        assert ChangeStats(files_changed=2, insertions=10, deletions=4).churn == 14

    @pytest.mark.parametrize("field", ["files_changed", "insertions", "deletions"])
    def test_rejects_negative_counts(self, field: str) -> None:
        """Negative counts are impossible."""
        with pytest.raises(ValueError):
            ChangeStats(**{field: -1})


class TestCommitCoverage:
    """Coverage arithmetic and unmeasured semantics."""

    def test_percentage_is_over_eligible_not_total_files(self) -> None:
        """Ineligible files cannot lower coverage.

        A repository of a thousand images and ten parsed Python files has full
        coverage of what is parseable, and reporting one percent would be a
        misleading statement about the index.
        """
        coverage = CommitCoverage(files_total=1000, files_eligible=10, files_parsed=10)
        assert coverage.files_parsed_pct == 100.0

    def test_empty_eligible_set_reports_zero_not_an_error(self) -> None:
        """A repository with nothing parseable has zero coverage, not a division fault."""
        coverage = CommitCoverage(files_total=5, files_eligible=0, files_parsed=0)
        assert coverage.files_parsed_pct == 0.0

    def test_symbol_and_edge_measures_are_unmeasured_by_default(self) -> None:
        """Milestone 1 cannot measure symbols or edges, so it reports nothing.

        ``None`` and zero are different statements. Twin Spec section 9 requires the
        distinction, because a consumer treating "unmeasured" as "none present"
        would draw a false conclusion about the repository.
        """
        coverage = CommitCoverage(files_total=1, files_eligible=1, files_parsed=1)
        assert coverage.symbols_resolved_pct is None
        assert coverage.exact_edge_pct is None

    def test_exact_edge_percentage_once_measured(self) -> None:
        """The precision proxy of PRD section 12.2 is computed once edges exist."""
        coverage = CommitCoverage(
            files_total=1,
            files_eligible=1,
            files_parsed=1,
            exact_edges=80,
            total_edges=100,
        )
        assert coverage.exact_edge_pct == 80.0

    def test_symbol_percentage_once_measured(self) -> None:
        """Resolution coverage is computed once symbols exist."""
        coverage = CommitCoverage(
            files_total=1,
            files_eligible=1,
            files_parsed=1,
            symbols_total=50,
            symbols_resolved=45,
        )
        assert coverage.symbols_resolved_pct == 90.0

    def test_zero_edges_reports_zero_rather_than_none(self) -> None:
        """A measured absence of edges is distinct from no measurement."""
        coverage = CommitCoverage(
            files_total=1,
            files_eligible=1,
            files_parsed=1,
            exact_edges=0,
            total_edges=0,
        )
        assert coverage.exact_edge_pct == 0.0

    def test_rejects_parsed_exceeding_eligible(self) -> None:
        """Coverage above one hundred percent is impossible."""
        with pytest.raises(ValueError, match="files_parsed cannot exceed"):
            CommitCoverage(files_total=10, files_eligible=5, files_parsed=6)

    def test_rejects_eligible_exceeding_total(self) -> None:
        """More eligible files than files present is impossible."""
        with pytest.raises(ValueError, match="files_eligible cannot exceed"):
            CommitCoverage(files_total=5, files_eligible=6, files_parsed=1)

    def test_language_breakdown_is_indexable(self) -> None:
        """Per-language coverage is addressable by language name."""
        coverage = CommitCoverage(
            files_total=4,
            files_eligible=4,
            files_parsed=3,
            by_language=(
                LanguageCoverage(language="python", files_total=2, files_parsed=2),
                LanguageCoverage(language="typescript", files_total=2, files_parsed=1),
            ),
        )
        index = coverage.language_index()
        assert index["python"].files_parsed_pct == 100.0
        assert index["typescript"].files_parsed_pct == 50.0


class TestLanguageCoverage:
    """Validation of the per-language breakdown."""

    def test_rejects_parsed_exceeding_total(self) -> None:
        """A language cannot parse more files than it has."""
        with pytest.raises(ValueError, match="cannot exceed"):
            LanguageCoverage(language="python", files_total=1, files_parsed=2)

    def test_rejects_blank_language(self) -> None:
        """A breakdown entry must name its language."""
        with pytest.raises(ValueError):
            LanguageCoverage(language="", files_total=1, files_parsed=1)

    def test_zero_files_reports_zero_percent(self) -> None:
        """A language with no files has zero coverage rather than a division fault."""
        assert (
            LanguageCoverage(
                language="python", files_total=0, files_parsed=0
            ).files_parsed_pct
            == 0.0
        )


class TestCommitRef:
    """The resolved pointer returned by ref resolution."""

    def test_retains_what_was_asked_for(self) -> None:
        """A resolved pointer records the expression as well as the result.

        Without it, a cached or logged resolution cannot be interpreted later.
        """
        reference = CommitRef(sha=CommitSha(SHA), ref="main", is_symbolic=True)
        assert reference.ref == "main"
        assert str(reference) == f"main@{CommitSha(SHA).short}"

    def test_renders_a_bare_sha_without_a_ref(self) -> None:
        """A direct object name has no symbolic expression to display."""
        reference = CommitRef(sha=CommitSha(SHA))
        assert str(reference) == CommitSha(SHA).short


class TestPersonRef:
    """Normalisation of an unresolved authorship signature."""

    def test_lowercases_and_trims_email(self) -> None:
        """Email is the stable identity key, so it is normalised once."""
        person = PersonRef(name="  Ada Lovelace  ", email="  Ada@Example.COM ")
        assert person.name == "Ada Lovelace"
        assert person.email == "ada@example.com"

    def test_blank_email_becomes_none(self) -> None:
        """An empty signature field is absence, not an empty string."""
        assert PersonRef(name="Ada", email="   ").email is None

    def test_identity_key_prefers_email(self) -> None:
        """Email is far more stable than a display name."""
        assert PersonRef(name="Ada", email="ada@example.com").identity_key == (
            "ada@example.com"
        )

    def test_identity_key_falls_back_to_name(self) -> None:
        """A signature without an email still groups by name."""
        assert PersonRef(name="Ada Lovelace").identity_key == "ada lovelace"

    def test_identity_key_is_never_empty(self) -> None:
        """An empty signature still yields a usable grouping key."""
        assert PersonRef(name="", email=None).identity_key == "unknown"

    def test_display_form(self) -> None:
        """The display form is stable for log output."""
        assert (
            str(PersonRef(name="Ada", email="ada@example.com"))
            == "Ada <ada@example.com>"
        )
        assert str(PersonRef(name="", email=None)) == "unknown"
