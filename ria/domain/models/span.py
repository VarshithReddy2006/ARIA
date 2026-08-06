"""Source location value objects.

Implements the ``span`` field of Twin Spec section 3.2, entity ``Symbol``::

    span: {start_byte, end_byte, start_line, start_col, end_line, end_col}
    Byte offsets are authoritative.

Why byte offsets are authoritative
----------------------------------
A character offset depends on an encoding and a definition of "character"; a byte
offset does not. Source files in real repositories are not reliably UTF-8, contain
astral-plane characters, and are read by tools that disagree about whether a combining
mark is one position or two. Byte offsets are the only representation on which the
parser, the blob store and a later citation check can agree, which is what makes the
citation verification of Twin Spec section 7 possible at all.

Line and column are carried alongside because a human reads them and a diff aligns to
them, but they are derived: where the two disagree, bytes win.

Zero-based lines and columns
----------------------------
Positions are stored exactly as tree-sitter reports them: line and column both
zero-based. The alternative — normalising to the one-based lines an editor shows —
would put arithmetic in the adapter, and an off-by-one there is invisible in tests that
use the same conversion in both directions. Storing the raw value means the adapter
copies numbers and never computes them, and the single conversion for display lives in
:attr:`SourcePosition.display_line`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

__all__ = ["SourcePosition", "SourceSpan"]


@dataclass(frozen=True)
class SourcePosition:
    """One location in a source file.

    Attributes:
        byte: Zero-based byte offset from the start of the file. Authoritative.
        line: Zero-based line index.
        column: Zero-based column index, counted in bytes within the line rather than
            in characters, so that it remains consistent with :attr:`byte`.
    """

    byte: int
    line: int
    column: int

    def __post_init__(self) -> None:
        for name in ("byte", "line", "column"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(
                    f"{name} must be an integer, got {type(value).__name__}"
                )
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def display_line(self) -> int:
        """One-based line number, for presentation only.

        The single place zero-based storage is converted for human consumption. Never
        used for comparison or arithmetic, so it cannot introduce an off-by-one into
        stored data.
        """
        return self.line + 1

    def __lt__(self, other: "SourcePosition") -> bool:
        """Order by byte offset, which totally orders positions in one file."""
        if not isinstance(other, SourcePosition):
            return NotImplemented
        return self.byte < other.byte

    def __le__(self, other: "SourcePosition") -> bool:
        """Order by byte offset."""
        if not isinstance(other, SourcePosition):
            return NotImplemented
        return self.byte <= other.byte

    def __str__(self) -> str:
        return f"{self.display_line}:{self.column}"


@dataclass(frozen=True)
class SourceSpan:
    """A half-open byte range in a source file.

    The range is half-open: ``start`` is included and ``end`` is excluded, matching
    Python slicing so that ``source[span.start.byte : span.end.byte]`` yields exactly
    the span's text with no adjustment. A closed range would require every caller to
    add one, and every caller that forgot would truncate the last byte of every
    identifier.

    An empty span, where start equals end, is permitted: tree-sitter reports zero-width
    positions for missing nodes it inserted during error recovery, and refusing to
    represent them would mean discarding the diagnostic that says where a file is
    malformed.

    Attributes:
        start: Inclusive start position.
        end: Exclusive end position.
    """

    start: SourcePosition
    end: SourcePosition

    def __post_init__(self) -> None:
        if self.end.byte < self.start.byte:
            raise ValueError(
                f"span end byte ({self.end.byte}) precedes start byte ({self.start.byte})"
            )
        if (self.end.line, self.end.column) < (self.start.line, self.start.column):
            raise ValueError(
                f"span end position precedes start position: {self.start} -> {self.end}"
            )

    # -- construction ------------------------------------------------------

    @classmethod
    def of(
        cls,
        *,
        start_byte: int,
        end_byte: int,
        start_line: int,
        start_column: int,
        end_line: int,
        end_column: int,
    ) -> "SourceSpan":
        """Build a span from the six primitive values a parser reports.

        Keyword-only because six integers in a row are otherwise trivially
        transposable, and a transposed span is accepted silently by any validation
        that only checks ordering.

        Args:
            start_byte: Inclusive start offset.
            end_byte: Exclusive end offset.
            start_line: Zero-based start line.
            start_column: Zero-based start column.
            end_line: Zero-based end line.
            end_column: Zero-based end column.

        Returns:
            The span.

        Raises:
            ValueError: If any value is negative or the end precedes the start.
        """
        return cls(
            start=SourcePosition(byte=start_byte, line=start_line, column=start_column),
            end=SourcePosition(byte=end_byte, line=end_line, column=end_column),
        )

    @classmethod
    def empty_at(cls, position: SourcePosition) -> "SourceSpan":
        """Build a zero-width span at one position.

        Args:
            position: Where the span sits.
        """
        return cls(start=position, end=position)

    # -- measures ----------------------------------------------------------

    @property
    def byte_length(self) -> int:
        """Number of bytes the span covers."""
        return self.end.byte - self.start.byte

    @property
    def line_count(self) -> int:
        """Number of lines the span touches, at least one."""
        return self.end.line - self.start.line + 1

    @property
    def is_empty(self) -> bool:
        """Whether the span covers no bytes."""
        return self.byte_length == 0

    @property
    def is_single_line(self) -> bool:
        """Whether the span begins and ends on one line."""
        return self.start.line == self.end.line

    # -- relations ---------------------------------------------------------

    def contains(self, other: "SourceSpan") -> bool:
        """Whether this span fully encloses another.

        The relation extraction relies on to attach a nested declaration to its
        container without resolution: a method is the declaration whose span the
        class's span contains.

        Args:
            other: Candidate inner span.
        """
        return self.start.byte <= other.start.byte and other.end.byte <= self.end.byte

    def contains_byte(self, offset: int) -> bool:
        """Whether a byte offset falls inside the span.

        Args:
            offset: Zero-based byte offset.
        """
        return self.start.byte <= offset < self.end.byte

    def overlaps(self, other: "SourceSpan") -> bool:
        """Whether two spans share at least one byte.

        Empty spans never overlap anything, because they contain no bytes to share.
        Checked explicitly: the interval comparison alone reports a zero-width span
        inside another span as overlapping, which would make every error-recovery
        insertion appear to conflict with the construct it was inserted into.

        Args:
            other: Span to compare against.
        """
        if self.is_empty or other.is_empty:
            return False
        return self.start.byte < other.end.byte and other.start.byte < self.end.byte

    def slice_of(self, source: bytes) -> bytes:
        """Extract this span's bytes from the source it describes.

        The only sanctioned way to obtain a span's text. Nodes deliberately do not
        store their text — a 10M-line repository would otherwise hold a second copy of
        itself in memory — so extraction reads through here.

        Args:
            source: Complete file content the span was computed against.

        Returns:
            The bytes the span covers.

        Raises:
            ValueError: If the span extends past the end of the source, which means
                the span and the content do not describe the same file.
        """
        if self.end.byte > len(source):
            raise ValueError(
                f"span ends at byte {self.end.byte} but the source is "
                f"{len(source)} bytes; the span does not describe this content"
            )
        return source[self.start.byte : self.end.byte]

    def text_of(self, source: bytes, *, encoding: str = "utf-8") -> str:
        """Extract this span's text, replacing undecodable bytes.

        Undecodable bytes are replaced rather than raising, because a single file with
        a mixed encoding must not abort a build (SDD section 3, L2 failure modes). The
        byte form remains available through :meth:`slice_of` for any caller that needs
        fidelity over readability.

        Args:
            source: Complete file content.
            encoding: Encoding to decode with.

        Returns:
            The decoded text.
        """
        return self.slice_of(source).decode(encoding, errors="replace")

    # -- ordering ----------------------------------------------------------

    def sort_key(self) -> Tuple[int, int]:
        """Deterministic ordering key.

        Ordered by start ascending, then by end *descending*, so a container sorts
        before the declarations nested inside it. Extraction and every serialised
        artefact rely on that order being total and stable, since a non-deterministic
        order would change the tree digest between runs on identical input.
        """
        return (self.start.byte, -self.end.byte)

    def __str__(self) -> str:
        if self.is_single_line:
            return f"{self.start.display_line}:{self.start.column}-{self.end.column}"
        return f"{self.start}-{self.end}"
