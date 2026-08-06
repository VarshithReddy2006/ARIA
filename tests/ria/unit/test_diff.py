"""Tests for the change set value object and the change detection function.

Twin Spec section 6.1 makes the change set the input to every incremental build, so a
defect here is not a wrong answer to one question but the wrong work performed on
every later commit: a missed change means stale facts served as current, and a
spurious change means work done for nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.diff import compute_change_set
from ria.domain.models.change_set import ChangeSet, RenamedPath

HEAD = "b" * 40
BASE = "a" * 40


def h(marker: str) -> str:
    """Build a canonical content hash from a short marker.

    Args:
        marker: Distinguishing character.
    """
    return "sha256:" + (marker * 64)[:64]


class TestRenamedPath:
    """Invariants of a detected rename."""

    def test_accepts_two_distinct_paths_sharing_content(self) -> None:
        """A rename records both endpoints and the shared hash."""
        rename = RenamedPath(
            previous_path="a.py", current_path="b.py", content_hash=h("1")
        )
        assert str(rename) == "a.py -> b.py"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"previous_path": ""},
            {"current_path": ""},
            {"content_hash": ""},
        ],
    )
    def test_rejects_missing_components(self, overrides: dict) -> None:
        """Every component is required to interpret the rename."""
        arguments = {
            "previous_path": "a.py",
            "current_path": "b.py",
            "content_hash": h("1"),
        }
        arguments.update(overrides)
        with pytest.raises(ValueError):
            RenamedPath(**arguments)

    def test_rejects_identical_paths(self) -> None:
        """A path renamed to itself is not a change."""
        with pytest.raises(ValueError, match="distinct"):
            RenamedPath(previous_path="a.py", current_path="a.py", content_hash=h("1"))

    def test_is_immutable(self) -> None:
        """A rename cannot be edited after detection."""
        rename = RenamedPath(
            previous_path="a.py", current_path="b.py", content_hash=h("1")
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            rename.current_path = "c.py"  # type: ignore[misc]


class TestChangeSetConstruction:
    """Invariants of the change set itself."""

    def test_requires_a_head(self) -> None:
        """A change set names the commit it describes."""
        with pytest.raises(ValueError, match="head_sha"):
            ChangeSet(head_sha="")

    def test_rejects_identical_commits(self) -> None:
        """Comparing a commit to itself is not a diff."""
        with pytest.raises(ValueError, match="distinct"):
            ChangeSet(head_sha=HEAD, base_sha=HEAD)

    def test_without_a_base_everything_must_be_an_addition(self) -> None:
        """A first build cannot have modified or deleted anything.

        Permitting it would let a caller describe a state that cannot exist and then
        act on it, for example invalidating facts that were never recorded.
        """
        with pytest.raises(ValueError, match="every path is an addition"):
            ChangeSet(head_sha=HEAD, modified=frozenset({"a.py"}))

    @pytest.mark.parametrize(
        "first,second",
        [("added", "modified"), ("added", "deleted"), ("modified", "deleted")],
    )
    def test_categories_must_be_disjoint(self, first: str, second: str) -> None:
        """A path appears in exactly one category.

        Overlap would make a consumer parse a file twice, or invalidate a path it had
        just rebuilt.
        """
        with pytest.raises(ValueError, match="overlap"):
            ChangeSet(
                head_sha=HEAD,
                base_sha=BASE,
                **{first: frozenset({"a.py"}), second: frozenset({"a.py"})},
            )

    def test_a_rename_target_may_not_also_be_added(self) -> None:
        """A renamed path is not additionally an addition."""
        with pytest.raises(ValueError, match="rename targets"):
            ChangeSet(
                head_sha=HEAD,
                base_sha=BASE,
                added=frozenset({"b.py"}),
                renamed=(
                    RenamedPath(
                        previous_path="a.py", current_path="b.py", content_hash=h("1")
                    ),
                ),
            )

    def test_a_rename_source_may_not_also_be_deleted(self) -> None:
        """A renamed path's origin is not additionally a deletion."""
        with pytest.raises(ValueError, match="rename sources"):
            ChangeSet(
                head_sha=HEAD,
                base_sha=BASE,
                deleted=frozenset({"a.py"}),
                renamed=(
                    RenamedPath(
                        previous_path="a.py", current_path="b.py", content_hash=h("1")
                    ),
                ),
            )

    def test_rejects_two_renames_onto_one_target(self) -> None:
        """A path cannot arrive from two origins."""
        with pytest.raises(ValueError, match="target of two renames"):
            ChangeSet(
                head_sha=HEAD,
                base_sha=BASE,
                renamed=(
                    RenamedPath(
                        previous_path="a.py", current_path="c.py", content_hash=h("1")
                    ),
                    RenamedPath(
                        previous_path="b.py", current_path="c.py", content_hash=h("1")
                    ),
                ),
            )

    def test_renames_are_ordered_deterministically(self) -> None:
        """Ordering is stable, which the response caching of SDD section 5.5 needs."""
        changes = ChangeSet(
            head_sha=HEAD,
            base_sha=BASE,
            renamed=(
                RenamedPath(
                    previous_path="x.py", current_path="z.py", content_hash=h("2")
                ),
                RenamedPath(
                    previous_path="y.py", current_path="a.py", content_hash=h("1")
                ),
            ),
        )
        assert [rename.current_path for rename in changes.renamed] == ["a.py", "z.py"]


class TestDerivedWorkSets:
    """The sets later milestones actually consume."""

    def make(self) -> ChangeSet:
        """Build a change set covering every category."""
        return ChangeSet(
            head_sha=HEAD,
            base_sha=BASE,
            added=frozenset({"new.py"}),
            modified=frozenset({"edited.py"}),
            deleted=frozenset({"gone.py"}),
            renamed=(
                RenamedPath(
                    previous_path="old.py", current_path="moved.py", content_hash=h("1")
                ),
            ),
        )

    def test_reparse_excludes_renames(self) -> None:
        """A renamed file's content is unchanged, so its parse result still applies.

        This exclusion is the practical payoff of content addressing: moving a
        directory of a thousand files costs no parsing at all.
        """
        assert self.make().paths_requiring_reparse() == frozenset(
            {"new.py", "edited.py"}
        )

    def test_invalidation_uses_a_rename_s_previous_path(self) -> None:
        """Stale facts are recorded against the old path, so that is what is cleared."""
        assert self.make().paths_to_invalidate() == frozenset(
            {"edited.py", "gone.py", "old.py"}
        )

    def test_head_paths_touched_includes_renames(self) -> None:
        """A renamed path is touched even though it needs no reparse.

        Its manifest entry moves, so a consumer maintaining path-keyed data must act
        on it — which is a different question from whether to reparse.
        """
        assert self.make().head_paths_touched() == frozenset(
            {"new.py", "edited.py", "moved.py"}
        )

    def test_counts_omit_empty_categories(self) -> None:
        """Counts are suitable directly as metric labels and progress detail."""
        assert self.make().counts() == {
            "added": 1,
            "modified": 1,
            "deleted": 1,
            "renamed": 1,
        }
        assert ChangeSet(head_sha=HEAD).counts() == {}

    def test_total_counts_a_rename_once(self) -> None:
        """A rename is one affected path, not two."""
        assert self.make().total == 4

    def test_empty_and_full_rebuild_are_distinguishable(self) -> None:
        """No changes and no base are different statements."""
        empty = ChangeSet(head_sha=HEAD, base_sha=BASE)
        full = ChangeSet(head_sha=HEAD, added=frozenset({"a.py"}))
        assert empty.is_empty and not empty.is_full_rebuild
        assert full.is_full_rebuild and not full.is_empty


class TestComputeChangeSet:
    """Behaviour of the detection function."""

    def test_no_base_makes_everything_an_addition(self) -> None:
        """A first build reports every path as added."""
        changes = compute_change_set(
            head_sha=HEAD, current={"a.py": h("1"), "b.py": h("2")}
        )
        assert changes.is_full_rebuild
        assert changes.added == frozenset({"a.py", "b.py"})

    def test_identical_trees_produce_no_changes(self) -> None:
        """Re-ingesting an unchanged commit finds nothing to do."""
        tree = {"a.py": h("1")}
        changes = compute_change_set(
            head_sha=HEAD, current=tree, previous=dict(tree), base_sha=BASE
        )
        assert changes.is_empty

    def test_categorises_added_modified_and_deleted(self) -> None:
        """Each path lands in exactly one category."""
        changes = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"same.py": h("1"), "edited.py": h("9"), "new.py": h("3")},
            previous={"same.py": h("1"), "edited.py": h("2"), "gone.py": h("4")},
        )
        assert changes.added == frozenset({"new.py"})
        assert changes.modified == frozenset({"edited.py"})
        assert changes.deleted == frozenset({"gone.py"})

    def test_detects_a_pure_rename(self) -> None:
        """A moved file with identical content is a rename, not a delete plus an add."""
        content = h("1")
        changes = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"moved.py": content},
            previous={"original.py": content},
        )
        assert changes.added == frozenset()
        assert changes.deleted == frozenset()
        assert len(changes.renamed) == 1
        assert changes.renamed[0].previous_path == "original.py"
        assert changes.renamed[0].current_path == "moved.py"

    def test_a_move_with_an_edit_is_not_a_rename(self) -> None:
        """Changed content means the parse cache is not reusable.

        A similarity-based rename would claim it was, and would silently skip a
        reparse the content actually required. Narrower is correct here.
        """
        changes = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"moved.py": h("9")},
            previous={"original.py": h("1")},
        )
        assert changes.renamed == ()
        assert changes.added == frozenset({"moved.py"})
        assert changes.deleted == frozenset({"original.py"})

    def test_a_copy_is_not_a_rename(self) -> None:
        """If the original still exists, nothing moved.

        Reporting a rename would claim the original was removed when it was not, and a
        consumer would invalidate facts about a file that is still there.
        """
        content = h("1")
        changes = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"original.py": content, "copy.py": content},
            previous={"original.py": content},
        )
        assert changes.renamed == ()
        assert changes.added == frozenset({"copy.py"})

    def test_rename_pairing_is_deterministic(self) -> None:
        """Two identical files moved at once pair the same way on every run.

        Non-deterministic pairing would make the change set unstable between runs and
        break response caching.
        """
        content = h("1")
        first = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"z.py": content, "y.py": content},
            previous={"b.py": content, "a.py": content},
        )
        second = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"y.py": content, "z.py": content},
            previous={"a.py": content, "b.py": content},
        )
        assert [(r.previous_path, r.current_path) for r in first.renamed] == [
            (r.previous_path, r.current_path) for r in second.renamed
        ]

    def test_rename_detection_can_be_disabled(self) -> None:
        """A caller that must treat every new path as new may opt out."""
        content = h("1")
        changes = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"moved.py": content},
            previous={"original.py": content},
            detect_renames=False,
        )
        assert changes.renamed == ()
        assert changes.added == frozenset({"moved.py"})
        assert changes.deleted == frozenset({"original.py"})

    def test_categories_remain_disjoint_after_pairing(self) -> None:
        """Paired paths leave the added and deleted sets.

        The construction invariant would reject the result otherwise, so this test
        guards the pairing's bookkeeping rather than the entity's validation.
        """
        content = h("1")
        changes = compute_change_set(
            head_sha=HEAD,
            base_sha=BASE,
            current={"moved.py": content, "new.py": h("2")},
            previous={"original.py": content, "gone.py": h("3")},
        )
        assert changes.added == frozenset({"new.py"})
        assert changes.deleted == frozenset({"gone.py"})
        assert len(changes.renamed) == 1

    def test_requires_a_base_sha_alongside_a_previous_tree(self) -> None:
        """A change set that cannot name its base is not interpretable."""
        with pytest.raises(ValueError, match="requires base_sha"):
            compute_change_set(head_sha=HEAD, current={}, previous={})

    def test_requires_a_previous_tree_alongside_a_base_sha(self) -> None:
        """Naming a base without supplying it would silently report a full rebuild."""
        with pytest.raises(ValueError, match="requires a previous mapping"):
            compute_change_set(head_sha=HEAD, current={}, base_sha=BASE)

    def test_handles_empty_trees(self) -> None:
        """A commit with no eligible files is representable."""
        assert compute_change_set(head_sha=HEAD, current={}).is_empty

    def test_deleting_everything(self) -> None:
        """A commit that removed every file reports only deletions."""
        changes = compute_change_set(
            head_sha=HEAD, base_sha=BASE, current={}, previous={"a.py": h("1")}
        )
        assert changes.deleted == frozenset({"a.py"})
        assert changes.added == frozenset()
