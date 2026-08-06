"""Tests for the language-agnostic syntax tree.

The determinism tests are the point of this module. Milestone 3 requires that the same
file always produce the same AST, and a digest that is insensitive to a structural
difference would let that requirement pass while being false — so the digest is tested
for sensitivity to every field that distinguishes two trees, not merely for stability.
"""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.models.span import SourceSpan
from ria.domain.models.syntax_tree import MAX_TREE_DEPTH, SyntaxNode, SyntaxTree

CONTENT_HASH = "sha256:" + "a" * 64
SOURCE = b"def handler():\n    return 200\n"


def span(start: int, end: int, *, line: int = 0) -> SourceSpan:
    """Build a single-line span."""
    return SourceSpan.of(
        start_byte=start,
        end_byte=end,
        start_line=line,
        start_column=start,
        end_line=line,
        end_column=end,
    )


def node(kind: str, start: int, end: int, **overrides) -> SyntaxNode:
    """Build a node with a single-line span."""
    return SyntaxNode(kind=kind, span=span(start, end), **overrides)


def sample_tree() -> SyntaxTree:
    """Build a small tree resembling a parsed Python function."""
    name = node("identifier", 4, 11, field_name="name")
    body = node("block", 13, 29, field_name="body")
    function = SyntaxNode(
        kind="function_definition", span=span(0, 29), children=(name, body)
    )
    root = SyntaxNode(kind="module", span=span(0, 30), children=(function,))
    return SyntaxTree(
        language="python", root=root, content_hash=CONTENT_HASH, source_bytes=30
    )


class TestSyntaxNodeConstruction:
    """Invariants of a node."""

    def test_accepts_a_well_formed_node(self) -> None:
        """A node is a kind, a span and ordered children."""
        subject = node("identifier", 0, 5)
        assert subject.kind == "identifier"
        assert subject.is_leaf is True

    def test_rejects_an_empty_kind(self) -> None:
        """A node without a grammar kind cannot be interpreted."""
        with pytest.raises(ValueError, match="kind"):
            node("", 0, 5)

    def test_rejects_an_empty_field_name(self) -> None:
        """An empty field label is absence, not a label."""
        with pytest.raises(ValueError, match="field_name"):
            node("identifier", 0, 5, field_name="")

    def test_a_missing_node_must_be_zero_width(self) -> None:
        """Error recovery inserts nodes that cover no source.

        A missing node with a non-empty span claims text exists where the parser
        recorded that it does not, and any span-based extraction would then read
        neighbouring text as the missing construct.
        """
        with pytest.raises(ValueError, match="covers no source"):
            node("identifier", 0, 5, is_missing=True)

    def test_a_zero_width_missing_node_is_accepted(self) -> None:
        """The legitimate shape of an inserted node."""
        assert node("identifier", 5, 5, is_missing=True).span.is_empty is True

    def test_children_are_normalised_to_a_tuple(self) -> None:
        """A caller's list cannot mutate the node after construction.

        Ordered and immutable is what makes the tree deterministic; a mutable child
        collection would let a later walk observe a different shape.
        """
        children = [node("a", 0, 1)]
        subject = SyntaxNode(kind="root", span=span(0, 2), children=children)
        children.clear()
        assert len(subject.children) == 1
        assert isinstance(subject.children, tuple)

    def test_is_immutable(self) -> None:
        """A node cannot be edited after construction."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            node("a", 0, 1).kind = "b"  # type: ignore[misc]


class TestSyntaxNodeTraversal:
    """Walking and field access."""

    def test_walk_is_pre_order(self) -> None:
        """A container is yielded before its contents.

        Pre-order lets an extractor maintain a container stack in one pass, which is how
        a method is attached to its class without a second traversal.
        """
        tree = sample_tree()
        assert [item.kind for item in tree.walk()] == [
            "module",
            "function_definition",
            "identifier",
            "block",
        ]

    def test_walk_preserves_sibling_order(self) -> None:
        """Children are visited in source order, not reversed by the stack."""
        root = SyntaxNode(
            kind="root",
            span=span(0, 6),
            children=(node("a", 0, 2), node("b", 2, 4), node("c", 4, 6)),
        )
        assert [item.kind for item in root.walk()][1:] == ["a", "b", "c"]

    def test_walk_refuses_a_pathologically_deep_tree(self) -> None:
        """A depth bound produces a stated error rather than a stack exhaustion.

        A long chained expression can nest hundreds of levels; a ``RecursionError`` from
        library internals would not say which file caused it.
        """
        current = node("leaf", 0, 1)
        for _ in range(5):
            current = SyntaxNode(kind="wrap", span=span(0, 1), children=(current,))
        with pytest.raises(ValueError, match="maximum depth"):
            list(current.walk(max_depth=2))

    def test_field_lookup_finds_a_labelled_child(self) -> None:
        """The sanctioned way to reach a declaration's parts.

        Positional indexing works until a grammar update inserts a node, after which
        every extractor silently reads the wrong child.
        """
        function = sample_tree().root.children[0]
        assert function.child_by_field("name").kind == "identifier"
        assert function.child_by_field("absent") is None

    def test_children_by_field_returns_every_match(self) -> None:
        """Some grammars label several children with one field name."""
        root = SyntaxNode(
            kind="call",
            span=span(0, 8),
            children=(
                node("arg", 0, 2, field_name="argument"),
                node("arg", 3, 5, field_name="argument"),
            ),
        )
        assert len(root.children_by_field("argument")) == 2

    def test_named_children_excludes_anonymous_nodes(self) -> None:
        """Punctuation and keywords are retained but excluded from extraction."""
        root = SyntaxNode(
            kind="parameters",
            span=span(0, 6),
            children=(
                node("(", 0, 1, is_named=False),
                node("identifier", 1, 5),
                node(")", 5, 6, is_named=False),
            ),
        )
        assert [child.kind for child in root.named_children()] == ["identifier"]

    def test_children_of_kind(self) -> None:
        """Immediate children can be selected by grammar kind."""
        root = SyntaxNode(
            kind="body",
            span=span(0, 6),
            children=(node("a", 0, 2), node("b", 2, 4), node("a", 4, 6)),
        )
        assert len(root.children_of_kind("a")) == 2
        assert len(root.children_of_kind("a", "b")) == 3

    def test_first_descendant_excludes_the_node_itself(self) -> None:
        """A search for a kind must not return the node that started it.

        Otherwise a nested search for the same kind always returns immediately and never
        descends.
        """
        root = SyntaxNode(
            kind="block", span=span(0, 4), children=(node("block", 1, 3),)
        )
        found = root.first_descendant_of_kind("block")
        assert found is not None
        assert found.span.start.byte == 1

    def test_first_descendant_returns_none_when_absent(self) -> None:
        """Absence is reported rather than raised."""
        assert sample_tree().root.first_descendant_of_kind("class_definition") is None


class TestSyntaxNodeMeasures:
    """Counts, depth and error nodes."""

    def test_node_count_includes_the_root(self) -> None:
        """The count covers the whole subtree."""
        assert sample_tree().root.node_count() == 4

    def test_depth_counts_the_root_as_one(self) -> None:
        """A leaf alone has depth one, not zero."""
        assert node("leaf", 0, 1).depth() == 1
        assert sample_tree().root.depth() == 3

    def test_depth_refuses_a_pathologically_deep_tree(self) -> None:
        """The bound applies to depth measurement too."""
        current = node("leaf", 0, 1)
        for _ in range(5):
            current = SyntaxNode(kind="wrap", span=span(0, 1), children=(current,))
        with pytest.raises(ValueError, match="maximum depth"):
            current.depth(max_depth=2)

    def test_error_nodes_collects_errors_and_missing(self) -> None:
        """Both flags mark a place where a file stops being trustworthy."""
        root = SyntaxNode(
            kind="module",
            span=span(0, 6),
            children=(
                node("ERROR", 0, 2, is_error=True),
                node("identifier", 5, 5, is_missing=True),
                node("identifier", 2, 4),
            ),
        )
        assert len(root.error_nodes()) == 2


class TestDeterminism:
    """The property the milestone requires."""

    def test_identical_trees_digest_identically(self) -> None:
        """Two parses of the same bytes must agree."""
        assert sample_tree().structural_digest() == sample_tree().structural_digest()

    def test_the_digest_is_memoised_without_changing(self) -> None:
        """Repeated calls on one tree return the same value."""
        tree = sample_tree()
        assert tree.structural_digest() == tree.structural_digest()

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda n: dataclasses.replace(n, kind="other"), id="kind"),
            pytest.param(
                lambda n: dataclasses.replace(n, field_name="renamed"), id="field_name"
            ),
            pytest.param(lambda n: dataclasses.replace(n, span=span(1, 12)), id="span"),
            pytest.param(
                lambda n: dataclasses.replace(n, is_named=False), id="is_named"
            ),
            pytest.param(
                lambda n: dataclasses.replace(n, is_error=True), id="is_error"
            ),
        ],
    )
    def test_the_digest_is_sensitive_to_every_distinguishing_field(
        self, mutate
    ) -> None:
        """Any difference that makes two trees different must change the digest.

        A digest insensitive to one field would let the determinism requirement pass
        while being false for exactly the case that field describes.
        """
        original = node("identifier", 4, 11, field_name="name")
        assert mutate(original).structural_digest() != original.structural_digest()

    def test_the_digest_distinguishes_nesting_from_sibling_order(self) -> None:
        """Two children and one nested child must not serialise identically.

        This is why the digest emits an explicit close marker per node; without it the
        two shapes produce the same stream of node records.
        """
        siblings = SyntaxNode(
            kind="m", span=span(0, 4), children=(node("a", 0, 2), node("b", 2, 4))
        )
        nested = SyntaxNode(
            kind="m",
            span=span(0, 4),
            children=(
                SyntaxNode(kind="a", span=span(0, 2), children=(node("b", 2, 4),)),
            ),
        )
        assert siblings.structural_digest() != nested.structural_digest()

    def test_the_digest_is_sensitive_to_child_order(self) -> None:
        """Reordered siblings are a different tree."""
        first = SyntaxNode(
            kind="m", span=span(0, 4), children=(node("a", 0, 2), node("b", 2, 4))
        )
        second = SyntaxNode(
            kind="m", span=span(0, 4), children=(node("b", 2, 4), node("a", 0, 2))
        )
        assert first.structural_digest() != second.structural_digest()

    def test_the_tree_digest_includes_the_language(self) -> None:
        """The same bytes parsed as two languages legitimately differ.

        A digest ignoring the language would report two correct results as one
        inconsistency.
        """
        root = sample_tree().root
        first = SyntaxTree(
            language="typescript", root=root, content_hash=CONTENT_HASH, source_bytes=30
        )
        second = SyntaxTree(
            language="tsx", root=root, content_hash=CONTENT_HASH, source_bytes=30
        )
        assert first.structural_digest() != second.structural_digest()

    def test_the_tree_digest_includes_the_content_hash(self) -> None:
        """A tree is bound to the bytes it describes."""
        root = sample_tree().root
        first = SyntaxTree(
            language="python", root=root, content_hash=CONTENT_HASH, source_bytes=30
        )
        second = SyntaxTree(
            language="python",
            root=root,
            content_hash="sha256:" + "b" * 64,
            source_bytes=30,
        )
        assert first.structural_digest() != second.structural_digest()

    def test_the_tree_digest_includes_truncation(self) -> None:
        """A partial tree is not the same artefact as a complete one."""
        root = sample_tree().root
        complete = SyntaxTree(
            language="python", root=root, content_hash=CONTENT_HASH, source_bytes=30
        )
        partial = SyntaxTree(
            language="python",
            root=root,
            content_hash=CONTENT_HASH,
            source_bytes=30,
            truncated=True,
        )
        assert complete.structural_digest() != partial.structural_digest()


class TestSyntaxTree:
    """Invariants and accessors of a whole parsed file."""

    def test_accepts_a_well_formed_tree(self) -> None:
        """A tree is a language, a root, a content hash and a size."""
        tree = sample_tree()
        assert tree.node_count == 4
        assert tree.max_depth == 3
        assert tree.is_complete is True

    @pytest.mark.parametrize(
        "overrides,match",
        [
            ({"language": ""}, "language"),
            ({"content_hash": ""}, "content_hash"),
            ({"source_bytes": -1}, "source_bytes"),
        ],
    )
    def test_rejects_malformed_metadata(self, overrides: dict, match: str) -> None:
        """A tree must name its language, its content and its size."""
        arguments = {
            "language": "python",
            "root": node("module", 0, 0),
            "content_hash": CONTENT_HASH,
            "source_bytes": 0,
        }
        arguments.update(overrides)
        with pytest.raises(ValueError, match=match):
            SyntaxTree(**arguments)

    def test_rejects_a_root_extending_past_the_source(self) -> None:
        """A tree whose root exceeds the content describes a different file.

        Accepting it would let every span in the tree read past the end of the bytes it
        was supposedly computed from.
        """
        with pytest.raises(ValueError, match="does not describe this content"):
            SyntaxTree(
                language="python",
                root=node("module", 0, 100),
                content_hash=CONTENT_HASH,
                source_bytes=30,
            )

    def test_an_empty_file_is_representable(self) -> None:
        """A zero-byte file parses to a single empty root."""
        tree = SyntaxTree(
            language="python",
            root=node("module", 0, 0),
            content_hash=CONTENT_HASH,
            source_bytes=0,
        )
        assert tree.node_count == 1
        assert tree.has_errors is False

    def test_errors_do_not_make_a_tree_unusable(self) -> None:
        """A file with a syntax error still yields what parsed.

        SDD section 3 (L2) requires extracting whatever parsed rather than discarding the
        file, so errors reduce confidence rather than invalidating the artefact.
        """
        root = SyntaxNode(
            kind="module",
            span=span(0, 10),
            children=(node("ERROR", 0, 2, is_error=True), node("identifier", 2, 6)),
        )
        tree = SyntaxTree(
            language="python", root=root, content_hash=CONTENT_HASH, source_bytes=10
        )
        assert tree.has_errors is True
        assert tree.is_complete is False
        assert tree.node_count == 3

    def test_truncation_makes_a_tree_incomplete(self) -> None:
        """A truncated tree is detectable rather than silently partial."""
        tree = SyntaxTree(
            language="python",
            root=node("module", 0, 10),
            content_hash=CONTENT_HASH,
            source_bytes=10,
            truncated=True,
        )
        assert tree.is_complete is False

    def test_nodes_of_kind_selects_across_the_tree(self) -> None:
        """Selection is by grammar kind over the whole tree."""
        assert len(sample_tree().nodes_of_kind("identifier")) == 1
        assert len(sample_tree().nodes_of_kind("identifier", "block")) == 2

    def test_kind_histogram_counts_every_node(self) -> None:
        """The histogram sums to the node count.

        Also the cheapest way for a plugin author to discover what a grammar emits for a
        construct before writing a query against it.
        """
        histogram = sample_tree().kind_histogram()
        assert sum(histogram.values()) == sample_tree().node_count
        assert histogram["identifier"] == 1

    def test_node_at_byte_returns_the_deepest_container(self) -> None:
        """Position lookup descends to the innermost node."""
        assert sample_tree().node_at_byte(5).kind == "identifier"

    def test_node_at_byte_outside_the_tree_is_none(self) -> None:
        """An offset past the file has no node."""
        assert sample_tree().node_at_byte(999) is None

    def test_measures_are_memoised_and_excluded_from_equality(self) -> None:
        """Two trees with identical content compare equal after being measured.

        The memo cache is a performance detail; if it participated in equality, reading a
        tree's node count would change whether it equalled an unmeasured copy.
        """
        first = sample_tree()
        second = sample_tree()
        assert first.node_count == 4
        assert first == second

    def test_the_depth_bound_is_stated(self) -> None:
        """The bound is a named constant, not a literal buried in a walk."""
        assert MAX_TREE_DEPTH > 0
