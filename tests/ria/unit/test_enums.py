"""Tests for the lifecycle transition tables.

Twin Spec section 3.2 states each entity's lifecycle as prose. These tests are what
turn that prose into an enforced invariant, and they check the tables exhaustively
rather than sampling them: an accidentally permitted transition is the kind of defect
that produces a corrupt timeline months later, with no way to reconstruct what the
correct state was.
"""

from __future__ import annotations

import itertools

import pytest

from ria.domain.enums import (
    COMMIT_INDEX_TRANSITIONS,
    REPOSITORY_TRANSITIONS,
    CommitIndexState,
    Facet,
    FileClassification,
    ParseStatus,
    RepositoryStatus,
    ResolutionMethod,
    assert_transition,
)
from ria.domain.errors import IllegalStateTransitionError


class TestTransitionTables:
    """Structural properties every transition table must have."""

    @pytest.mark.parametrize(
        "enumeration,table",
        [
            (RepositoryStatus, REPOSITORY_TRANSITIONS),
            (CommitIndexState, COMMIT_INDEX_TRANSITIONS),
        ],
    )
    def test_every_state_has_an_entry(self, enumeration, table) -> None:
        """No state may be missing from its table.

        A missing entry silently behaves as a terminal state, which would strand an
        entity rather than raising where the defect is.
        """
        assert set(table) == set(enumeration)

    @pytest.mark.parametrize(
        "table", [REPOSITORY_TRANSITIONS, COMMIT_INDEX_TRANSITIONS]
    )
    def test_no_table_permits_a_self_transition(self, table) -> None:
        """Self-transitions are handled by the validator, not by the table."""
        for state, targets in table.items():
            assert state not in targets

    @pytest.mark.parametrize(
        "enumeration,table",
        [
            (RepositoryStatus, REPOSITORY_TRANSITIONS),
            (CommitIndexState, COMMIT_INDEX_TRANSITIONS),
        ],
    )
    def test_every_target_is_a_member(self, enumeration, table) -> None:
        """Targets are members of the same enumeration."""
        for targets in table.values():
            assert targets <= set(enumeration)


class TestAssertTransition:
    """Behaviour of :func:`~ria.domain.enums.assert_transition`."""

    def test_permits_a_declared_transition(self) -> None:
        """A transition present in the table is accepted."""
        assert_transition(
            "Commit",
            CommitIndexState.PENDING,
            CommitIndexState.INDEXING,
            COMMIT_INDEX_TRANSITIONS,
        )

    def test_permits_a_self_transition_as_a_no_op(self) -> None:
        """Re-requesting the current state succeeds.

        Required for idempotency: a retried job must be able to assert its target
        state without knowing whether a previous attempt already reached it.
        """
        assert_transition(
            "Commit",
            CommitIndexState.QUERYABLE,
            CommitIndexState.QUERYABLE,
            COMMIT_INDEX_TRANSITIONS,
        )

    def test_rejects_an_undeclared_transition_with_context(self) -> None:
        """A rejected transition names the entity and both states."""
        with pytest.raises(IllegalStateTransitionError) as caught:
            assert_transition(
                "Commit",
                CommitIndexState.DISCOVERED,
                CommitIndexState.QUERYABLE,
                COMMIT_INDEX_TRANSITIONS,
            )
        error = caught.value
        assert error.entity == "Commit"
        assert error.current == "discovered"
        assert error.requested == "queryable"


class TestRepositoryLifecycle:
    """The repository lifecycle of Twin Spec section 3.2."""

    def test_registered_may_begin_indexing(self) -> None:
        """Registration is followed by a first index build."""
        assert (
            RepositoryStatus.INDEXING
            in REPOSITORY_TRANSITIONS[RepositoryStatus.REGISTERED]
        )

    def test_active_and_degraded_are_mutually_reachable(self) -> None:
        """Degradation is recoverable in both directions."""
        assert (
            RepositoryStatus.DEGRADED in REPOSITORY_TRANSITIONS[RepositoryStatus.ACTIVE]
        )
        assert (
            RepositoryStatus.ACTIVE in REPOSITORY_TRANSITIONS[RepositoryStatus.DEGRADED]
        )

    def test_paused_may_be_resumed(self) -> None:
        """A paused repository can return to service."""
        assert (
            RepositoryStatus.ACTIVE in REPOSITORY_TRANSITIONS[RepositoryStatus.PAUSED]
        )

    def test_archived_is_terminal(self) -> None:
        """Archival ends the lifecycle; the only next step is a purge, which deletes."""
        assert REPOSITORY_TRANSITIONS[RepositoryStatus.ARCHIVED] == frozenset()

    def test_every_live_state_can_be_archived(self) -> None:
        """Archival is always reachable, so a repository can never be stranded."""
        for state in RepositoryStatus:
            if state is RepositoryStatus.ARCHIVED:
                continue
            assert RepositoryStatus.ARCHIVED in REPOSITORY_TRANSITIONS[state], state


class TestCommitLifecycle:
    """The commit index lifecycle of Twin Spec section 3.2."""

    def test_happy_path_is_a_single_chain(self) -> None:
        """Discovery to queryable proceeds one step at a time."""
        chain = [
            CommitIndexState.DISCOVERED,
            CommitIndexState.PENDING,
            CommitIndexState.INDEXING,
            CommitIndexState.QUERYABLE,
        ]
        for current, following in zip(chain, chain[1:]):
            assert following in COMMIT_INDEX_TRANSITIONS[current]

    def test_no_state_skips_straight_to_queryable(self) -> None:
        """Only ``INDEXING`` may produce a queryable commit.

        This is the atomic visibility rule of SDD section 5.1: a commit becomes
        visible only when a build completes, never by any other path.
        """
        for state in CommitIndexState:
            if state in (CommitIndexState.INDEXING, CommitIndexState.QUERYABLE):
                continue
            assert CommitIndexState.QUERYABLE not in COMMIT_INDEX_TRANSITIONS[state], (
                state
            )

    def test_failure_is_retryable(self) -> None:
        """A failed commit may be re-queued, so a transient fault is recoverable."""
        assert (
            CommitIndexState.PENDING
            in COMMIT_INDEX_TRANSITIONS[CommitIndexState.FAILED]
        )

    def test_queryable_may_only_become_orphaned(self) -> None:
        """A queryable commit cannot be re-indexed into another state.

        Its facts are frozen, so any further movement would contradict the record
        already served to consumers.
        """
        assert COMMIT_INDEX_TRANSITIONS[CommitIndexState.QUERYABLE] == frozenset(
            {CommitIndexState.ORPHANED}
        )

    def test_orphaned_is_terminal(self) -> None:
        """Orphaned commits retain their facts forever and never move again."""
        assert COMMIT_INDEX_TRANSITIONS[CommitIndexState.ORPHANED] == frozenset()

    @pytest.mark.parametrize(
        "state,queryable",
        [
            (CommitIndexState.DISCOVERED, False),
            (CommitIndexState.PENDING, False),
            (CommitIndexState.INDEXING, False),
            (CommitIndexState.QUERYABLE, True),
            (CommitIndexState.FAILED, False),
            (CommitIndexState.ORPHANED, False),
        ],
    )
    def test_only_queryable_serves_facts(
        self, state: CommitIndexState, queryable: bool
    ) -> None:
        """An orphaned commit retains facts but no longer serves them."""
        assert state.is_queryable is queryable

    @pytest.mark.parametrize(
        "state,frozen",
        [
            (CommitIndexState.DISCOVERED, False),
            (CommitIndexState.PENDING, False),
            (CommitIndexState.INDEXING, False),
            (CommitIndexState.QUERYABLE, True),
            (CommitIndexState.FAILED, False),
            (CommitIndexState.ORPHANED, True),
        ],
    )
    def test_facts_freeze_once_queryable(
        self, state: CommitIndexState, frozen: bool
    ) -> None:
        """Facts freeze at ``QUERYABLE`` and stay frozen through ``ORPHANED``."""
        assert state.facts_are_frozen is frozen

    def test_no_pair_of_states_is_bidirectional_except_failure_retry(self) -> None:
        """The lifecycle is a forward progression apart from the failure retry.

        A cycle anywhere else would let a commit oscillate, making its history
        ambiguous.
        """
        bidirectional = {
            (first, second)
            for first, second in itertools.permutations(CommitIndexState, 2)
            if second in COMMIT_INDEX_TRANSITIONS[first]
            and first in COMMIT_INDEX_TRANSITIONS[second]
        }
        assert bidirectional == {
            (CommitIndexState.PENDING, CommitIndexState.FAILED),
            (CommitIndexState.FAILED, CommitIndexState.PENDING),
        }


class TestParseStatus:
    """Coverage semantics of :class:`~ria.domain.enums.ParseStatus`."""

    @pytest.mark.parametrize(
        "status,counts",
        [
            (ParseStatus.PENDING, False),
            (ParseStatus.PARSED, True),
            (ParseStatus.PARTIAL, True),
            (ParseStatus.UNPARSEABLE, False),
            (ParseStatus.SKIPPED, False),
        ],
    )
    def test_coverage_contribution(self, status: ParseStatus, counts: bool) -> None:
        """A partially parsed file contributes; an unparsed one does not.

        ``PENDING`` deliberately does not count. Reporting a not-yet-parsed file as
        covered would overstate what the index understands, which PRD principle P11
        forbids.
        """
        assert status.contributes_to_coverage is counts


class TestValueEnums:
    """String value stability of the remaining enumerations."""

    def test_resolution_methods_are_ordered_by_strength(self) -> None:
        """Rank ordering lets tier merging prefer the stronger observation."""
        assert (
            ResolutionMethod.HEURISTIC.rank
            < ResolutionMethod.INFERRED.rank
            < ResolutionMethod.EXACT.rank
        )

    def test_facets_match_the_specification(self) -> None:
        """The five facets of Twin Spec section 1.2, no more and no fewer."""
        assert {facet.value for facet in Facet} == {
            "structure",
            "history",
            "runtime",
            "intent",
            "social",
        }

    @pytest.mark.parametrize(
        "member,value",
        [
            (RepositoryStatus.ACTIVE, "active"),
            (CommitIndexState.QUERYABLE, "queryable"),
            (ParseStatus.PARSED, "parsed"),
            (FileClassification.SOURCE, "source"),
            (Facet.STRUCTURE, "structure"),
        ],
    )
    def test_stored_values_are_stable(self, member, value: str) -> None:
        """Persisted values are part of the storage contract and must not drift.

        These strings are written to the database, so renaming one is a migration,
        not a refactor.
        """
        assert member.value == value
        assert str(member) == value

    def test_ingestion_stage_parse_order(self) -> None:
        """IngestionStage.PARSE must sit between DETECT_CHANGES and PERSIST."""
        from ria.domain.enums import IngestionStage

        assert IngestionStage.PARSE.value == "parse"
        assert (
            IngestionStage.DETECT_CHANGES.order
            < IngestionStage.PARSE.order
            < IngestionStage.PERSIST.order
        )
