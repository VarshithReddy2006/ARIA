"""Language-agnostic syntax tree.

The domain's representation of a parsed file. Nothing above the parser adapter ever
holds a tree-sitter object: SDD section 7 adopts Hexagonal architecture, and a
third-party parse tree leaking into the domain would make the grammar library a domain
dependency and every consumer of a tree unable to run without it.

Determinism
-----------
Milestone 3 requires that the same file always produce the same tree. Two properties
deliver it, and :meth:`SyntaxTree.structural_digest` makes it assertable rather than
asserted:

* children are an ordered tuple, in source order, never a set or a mapping;
* nothing in a node depends on wall-clock time, iteration order, or identity.

The digest covers structure and position but not source text, so it answers "did the
parser produce the same shape" without depending on how text is decoded.

No text in nodes
----------------
A node carries a :class:`~ria.domain.models.span.SourceSpan` and no text. Storing text
would hold a second copy of the repository in memory — at the 10M-LOC scale of SDD
section 1.1 that is tens of gigabytes for no gain, because the bytes are already in the
content-addressable store. Callers read text through
:meth:`~ria.domain.models.span.SourceSpan.slice_of`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterator, Mapping, Optional, Tuple

from ria.domain.models.span import SourceSpan

__all__ = ["SyntaxNode", "SyntaxTree"]

#: Maximum depth the recursive helpers will descend before refusing to continue.
#: Deeply nested expressions — a long chained call, a large literal — produce trees
#: that would exhaust the interpreter's stack. Refusing loudly at a stated bound beats
#: a ``RecursionError`` raised from library internals with no indication of which file
#: caused it.
MAX_TREE_DEPTH = 500


@dataclass(frozen=True)
class SyntaxNode:
    """One node of a parsed syntax tree.

    Attributes:
        kind: Grammar node type, for example ``function_definition``. Verbatim from the
            grammar rather than normalised: normalising would require a per-language
            translation table that is itself a semantic judgement, and Milestone 3 is
            syntax only. Extractors interpret these strings; nothing else does.
        span: Where the node sits in the source.
        children: Child nodes in source order.
        field_name: The grammar field this node fills in its parent, for example
            ``name`` or ``body``. Present only when the parent labels the slot. This is
            what lets an extractor ask for a declaration's name field instead of
            guessing at a child index, which changes between grammar versions.
        is_named: Whether the grammar considers the node named. Anonymous nodes are
            punctuation and keywords; extraction ignores them, and keeping them lets a
            span cover its delimiters.
        is_error: Whether the parser recorded an error at this node.
        is_missing: Whether the parser inserted this node during error recovery, so it
            has a zero-width span and no corresponding source text.
    """

    kind: str
    span: SourceSpan
    children: Tuple["SyntaxNode", ...] = ()
    field_name: Optional[str] = None
    is_named: bool = True
    is_error: bool = False
    is_missing: bool = False

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("node kind must be non-empty")
        if self.field_name is not None and not self.field_name:
            raise ValueError("field_name must be non-empty when present")
        object.__setattr__(self, "children", tuple(self.children))
        if self.is_missing and not self.span.is_empty:
            raise ValueError(
                "a missing node is inserted by error recovery and covers no source, "
                f"but its span covers {self.span.byte_length} bytes"
            )

    # -- traversal ---------------------------------------------------------

    def walk(self, *, max_depth: int = MAX_TREE_DEPTH) -> Iterator["SyntaxNode"]:
        """Yield this node and every descendant, in pre-order.

        Iterative rather than recursive, so a pathologically nested file produces a
        stated error at the bound instead of exhausting the interpreter stack inside a
        generator frame.

        Pre-order matters: a container is yielded before its contents, so an extractor
        walking once can maintain a container stack and attach nested declarations
        without a second pass.

        Args:
            max_depth: Depth at which to refuse to descend further.

        Yields:
            Nodes in pre-order.

        Raises:
            ValueError: If the tree is deeper than ``max_depth``.
        """
        stack: list = [(self, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > max_depth:
                raise ValueError(
                    f"syntax tree exceeds the maximum depth of {max_depth} at node "
                    f"{node.kind!r}; the file is too deeply nested to process"
                )
            yield node
            for child in reversed(node.children):
                stack.append((child, depth + 1))

    def named_children(self) -> Tuple["SyntaxNode", ...]:
        """Children the grammar considers named, in source order."""
        return tuple(child for child in self.children if child.is_named)

    def child_by_field(self, field_name: str) -> Optional["SyntaxNode"]:
        """The first child filling a named grammar field.

        The sanctioned way to reach a declaration's parts. Indexing into
        :attr:`children` positionally works until a grammar update inserts a node, at
        which point every extractor silently reads the wrong child.

        Args:
            field_name: Grammar field name, for example ``name``.

        Returns:
            The child, or ``None`` if the field is absent.
        """
        for child in self.children:
            if child.field_name == field_name:
                return child
        return None

    def children_by_field(self, field_name: str) -> Tuple["SyntaxNode", ...]:
        """Every child filling a named grammar field, in source order.

        Args:
            field_name: Grammar field name.
        """
        return tuple(child for child in self.children if child.field_name == field_name)

    def children_of_kind(self, *kinds: str) -> Tuple["SyntaxNode", ...]:
        """Immediate children of any of the given grammar kinds, in source order.

        Args:
            *kinds: Grammar node types to match.
        """
        wanted = frozenset(kinds)
        return tuple(child for child in self.children if child.kind in wanted)

    def first_descendant_of_kind(
        self, *kinds: str, max_depth: int = MAX_TREE_DEPTH
    ) -> Optional["SyntaxNode"]:
        """First descendant of any given kind in pre-order, or ``None``.

        Args:
            *kinds: Grammar node types to match.
            max_depth: Depth bound for the walk.
        """
        wanted = frozenset(kinds)
        for node in self.walk(max_depth=max_depth):
            if node is not self and node.kind in wanted:
                return node
        return None

    # -- measures ----------------------------------------------------------

    @property
    def is_leaf(self) -> bool:
        """Whether the node has no children."""
        return not self.children

    def node_count(self, *, max_depth: int = MAX_TREE_DEPTH) -> int:
        """Total nodes in this subtree, including this node.

        Args:
            max_depth: Depth bound for the walk.
        """
        return sum(1 for _ in self.walk(max_depth=max_depth))

    def depth(self, *, max_depth: int = MAX_TREE_DEPTH) -> int:
        """Depth of this subtree, counting this node as one.

        Args:
            max_depth: Depth bound before refusing to descend further.

        Raises:
            ValueError: If the subtree is deeper than ``max_depth``.
        """
        deepest = 0
        stack: list = [(self, 1)]
        while stack:
            node, level = stack.pop()
            if level > max_depth:
                raise ValueError(
                    f"syntax tree exceeds the maximum depth of {max_depth} at node "
                    f"{node.kind!r}"
                )
            deepest = max(deepest, level)
            for child in node.children:
                stack.append((child, level + 1))
        return deepest

    def error_nodes(
        self, *, max_depth: int = MAX_TREE_DEPTH
    ) -> Tuple["SyntaxNode", ...]:
        """Every node in this subtree the parser flagged as an error or missing.

        The input to parse diagnostics: a node the parser could not fit into the
        grammar is where a file stops being trustworthy.

        Args:
            max_depth: Depth bound for the walk.
        """
        return tuple(
            node
            for node in self.walk(max_depth=max_depth)
            if node.is_error or node.is_missing
        )

    # -- determinism -------------------------------------------------------

    def _digest_parts(self, *, max_depth: int) -> Iterator[bytes]:
        """Yield the byte fragments contributing to a structural digest.

        Emits an explicit close marker per node so that two differently shaped trees
        cannot serialise identically. Without it, a node with two children and a node
        with one child that itself has one child would produce the same stream.

        Args:
            max_depth: Depth bound.
        """
        stack: list = [(self, 0, False)]
        while stack:
            node, depth, closing = stack.pop()
            if closing:
                yield b")"
                continue
            if depth > max_depth:
                raise ValueError(
                    f"syntax tree exceeds the maximum depth of {max_depth} at node "
                    f"{node.kind!r}"
                )
            yield b"("
            yield node.kind.encode("utf-8")
            yield b"\x1f"
            yield (node.field_name or "").encode("utf-8")
            yield b"\x1f"
            yield b"".join(
                (
                    str(node.span.start.byte).encode("ascii"),
                    b",",
                    str(node.span.end.byte).encode("ascii"),
                    b",",
                    str(node.span.start.line).encode("ascii"),
                    b",",
                    str(node.span.start.column).encode("ascii"),
                    b",",
                    str(node.span.end.line).encode("ascii"),
                    b",",
                    str(node.span.end.column).encode("ascii"),
                )
            )
            yield b"\x1f"
            yield b"".join(
                (
                    b"1" if node.is_named else b"0",
                    b"1" if node.is_error else b"0",
                    b"1" if node.is_missing else b"0",
                )
            )
            stack.append((node, depth, True))
            for child in reversed(node.children):
                stack.append((child, depth + 1, False))

    def structural_digest(self, *, max_depth: int = MAX_TREE_DEPTH) -> str:
        """Stable digest of this subtree's shape and positions.

        Two parses of identical bytes by identical parser versions must produce equal
        digests, and any difference in shape, position or flags must produce different
        ones. This is what turns the milestone's determinism requirement into a single
        assertion instead of a structural comparison a test could get wrong.

        Source text is excluded on purpose: the digest answers whether the parser
        produced the same tree, which is independent of how bytes decode.

        Args:
            max_depth: Depth bound for the walk.

        Returns:
            Hexadecimal SHA-256 digest.
        """
        digest = hashlib.sha256()
        for part in self._digest_parts(max_depth=max_depth):
            digest.update(part)
        return digest.hexdigest()

    def __str__(self) -> str:
        label = f"{self.field_name}: " if self.field_name else ""
        return f"{label}{self.kind}@{self.span} ({len(self.children)} children)"


@dataclass(frozen=True)
class SyntaxTree:
    """A complete parsed file.

    Attributes:
        language: Canonical language name the file was parsed as, matching
            :class:`~ria.domain.language.LanguageCatalogue`.
        root: Root node.
        content_hash: Canonical content hash of the bytes parsed, as a string. Binds
            the tree to the exact content it describes, so a cached tree can never be
            served for different bytes and a span can be verified against the source
            it was computed from.
        source_bytes: Size of the parsed content.
        truncated: Whether parsing stopped early, for example on a parser timeout. A
            truncated tree describes part of a file and must never be presented as
            complete; the flag exists so an accidental partial tree is detectable
            rather than to license producing one.
    """

    language: str
    root: SyntaxNode
    content_hash: str
    source_bytes: int
    truncated: bool = False

    #: Lazily computed node statistics, excluded from equality and construction.
    _measures: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.language:
            raise ValueError("language must be non-empty")
        if not self.content_hash:
            raise ValueError(
                "content_hash must be present so the tree is bound to the bytes it "
                "describes"
            )
        if self.source_bytes < 0:
            raise ValueError(
                f"source_bytes must be non-negative, got {self.source_bytes}"
            )
        if self.root.span.end.byte > self.source_bytes:
            raise ValueError(
                f"root span ends at byte {self.root.span.end.byte} but the source is "
                f"{self.source_bytes} bytes; the tree does not describe this content"
            )

    # -- measures ----------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Total nodes in the tree.

        Computed once and memoised: a large file's tree is walked by several consumers
        and the count does not change, the tree being immutable.
        """
        cached = self._measures.get("node_count")
        if cached is None:
            cached = self.root.node_count()
            self._measures["node_count"] = cached
        return cached

    @property
    def max_depth(self) -> int:
        """Depth of the tree, counting the root as one."""
        cached = self._measures.get("max_depth")
        if cached is None:
            cached = self.root.depth()
            self._measures["max_depth"] = cached
        return cached

    @property
    def has_errors(self) -> bool:
        """Whether the parser flagged any node as an error or missing.

        A tree with errors is still useful: SDD section 3 (L2) requires extracting
        whatever parsed rather than discarding the file, so this reports reduced
        confidence rather than failure.
        """
        return bool(self.error_nodes)

    @property
    def error_nodes(self) -> Tuple[SyntaxNode, ...]:
        """Every node the parser flagged as an error or missing."""
        cached = self._measures.get("error_nodes")
        if cached is None:
            cached = self.root.error_nodes()
            self._measures["error_nodes"] = cached
        return cached

    @property
    def is_complete(self) -> bool:
        """Whether the tree describes the whole file with no parse errors."""
        return not self.truncated and not self.has_errors

    # -- traversal ---------------------------------------------------------

    def walk(self) -> Iterator[SyntaxNode]:
        """Yield every node in pre-order, root first."""
        return self.root.walk()

    def nodes_of_kind(self, *kinds: str) -> Tuple[SyntaxNode, ...]:
        """Every node of any given grammar kind, in pre-order.

        Args:
            *kinds: Grammar node types to match.
        """
        wanted = frozenset(kinds)
        return tuple(node for node in self.walk() if node.kind in wanted)

    def kind_histogram(self) -> Mapping[str, int]:
        """Count of nodes per grammar kind.

        Serves two purposes: parse statistics, and a cheap way for a plugin author to
        discover what a grammar actually emits for a construct before writing a query
        against it.
        """
        histogram: dict = {}
        for node in self.walk():
            histogram[node.kind] = histogram.get(node.kind, 0) + 1
        return histogram

    def node_at_byte(self, offset: int) -> Optional[SyntaxNode]:
        """The deepest node whose span contains a byte offset.

        Args:
            offset: Zero-based byte offset.

        Returns:
            The innermost containing node, or ``None`` if the offset is outside the
            tree.
        """
        if not self.root.span.contains_byte(offset):
            return None
        current = self.root
        while True:
            for child in current.children:
                if child.span.contains_byte(offset):
                    current = child
                    break
            else:
                return current

    # -- determinism -------------------------------------------------------

    def structural_digest(self) -> str:
        """Stable digest of the whole tree, including its language.

        The language participates because the same bytes parsed as TypeScript and as
        TSX legitimately produce different trees, and a digest that ignored it would
        report two correct results as one inconsistency.

        Returns:
            Hexadecimal SHA-256 digest.
        """
        cached = self._measures.get("structural_digest")
        if cached is None:
            digest = hashlib.sha256()
            digest.update(self.language.encode("utf-8"))
            digest.update(b"\x1e")
            digest.update(self.content_hash.encode("utf-8"))
            digest.update(b"\x1e")
            digest.update(b"1" if self.truncated else b"0")
            digest.update(b"\x1e")
            for part in self.root._digest_parts(max_depth=MAX_TREE_DEPTH):
                digest.update(part)
            cached = digest.hexdigest()
            self._measures["structural_digest"] = cached
        return cached

    def __str__(self) -> str:
        state = (
            "truncated" if self.truncated else ("errors" if self.has_errors else "ok")
        )
        return f"tree({self.language}, {self.node_count} nodes, {state})"
