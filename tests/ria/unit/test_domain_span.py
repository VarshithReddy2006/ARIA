"""Tests for source position and span value objects.

Spans are the foundation of every syntax artefact and of the citation verification of
Twin Spec section 7. An off-by-one here does not produce an error; it produces a citation
that points one character away from the truth, on every result, forever.
"""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.models.span import SourcePosition, SourceSpan

SOURCE = b"def handler():\n    return 200\n"


def span(start: int, end: int, *, line: int = 0) -> SourceSpan:
    """Build a single-line span for a test.

    Args:
        start: Inclusive start byte.
        end: Exclusive end byte.
        line: Zero-based line.
    """
    return SourceSpan.of(
        start_byte=start,
        end_byte=end,
        start_line=line,
        start_column=start,
        end_line=line,
        end_column=end,
    )


class TestSourcePosition:
    """Invariants of a single location."""

    def test_accepts_a_valid_position(self) -> None:
        """A position is three non-negative integers."""
        position = SourcePosition(byte=10, line=2, column=4)
        assert (position.byte, position.line, position.column) == (10, 2, 4)

    @pytest.mark.parametrize("field", ["byte", "line", "column"])
    def test_rejects_a_negative_component(self, field: str) -> None:
        """A negative offset cannot describe a location."""
        arguments = {"byte": 0, "line": 0, "column": 0}
        arguments[field] = -1
        with pytest.raises(ValueError, match=field):
            SourcePosition(**arguments)

    @pytest.mark.parametrize("value", [1.5, "3", None, True])
    def test_rejects_a_non_integer_component(self, value: object) -> None:
        """A float or a string offset is rejected rather than coerced.

        ``True`` is rejected explicitly: it is an ``int`` subclass, so a naive check
        would accept it and store a boolean as a byte offset.
        """
        with pytest.raises(ValueError):
            SourcePosition(byte=value, line=0, column=0)  # type: ignore[arg-type]

    def test_display_line_is_one_based(self) -> None:
        """The single conversion from storage to presentation.

        Storage is zero-based so the adapter copies tree-sitter's numbers without
        arithmetic; an editor shows one-based, so exactly one property converts.
        """
        assert SourcePosition(byte=0, line=0, column=0).display_line == 1
        assert SourcePosition(byte=0, line=41, column=0).display_line == 42

    def test_orders_by_byte_offset(self) -> None:
        """Byte offset totally orders positions within one file."""
        first = SourcePosition(byte=5, line=0, column=5)
        second = SourcePosition(byte=9, line=0, column=9)
        assert first < second
        assert first <= second
        assert not second < first

    def test_comparison_with_another_type_is_not_implemented(self) -> None:
        """Ordering against an unrelated type defers rather than guessing."""
        with pytest.raises(TypeError):
            _ = SourcePosition(byte=0, line=0, column=0) < 5

    def test_is_immutable(self) -> None:
        """A position cannot be edited after construction."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            SourcePosition(byte=0, line=0, column=0).byte = 1  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        """Positions are usable as keys and set members."""
        first = SourcePosition(byte=1, line=0, column=1)
        second = SourcePosition(byte=1, line=0, column=1)
        assert len({first, second}) == 1


class TestSourceSpanConstruction:
    """Invariants of a byte range."""

    def test_accepts_a_forward_range(self) -> None:
        """A span runs from a start to a later end."""
        assert span(0, 5).byte_length == 5

    def test_accepts_an_empty_span(self) -> None:
        """A zero-width span is representable.

        Error recovery inserts missing nodes at zero-width positions, and refusing to
        represent them would discard the diagnostic saying where a file is malformed.
        """
        assert span(7, 7).is_empty is True

    def test_rejects_a_reversed_byte_range(self) -> None:
        """An end before a start cannot describe a range."""
        with pytest.raises(ValueError, match="precedes start byte"):
            SourceSpan.of(
                start_byte=10,
                end_byte=4,
                start_line=0,
                start_column=10,
                end_line=0,
                end_column=4,
            )

    def test_rejects_a_reversed_line_range(self) -> None:
        """Line and column ordering is validated as well as byte ordering.

        Bytes are authoritative, but a span whose line positions contradict its bytes
        describes two different locations and would misplace a citation.
        """
        with pytest.raises(ValueError, match="precedes start position"):
            SourceSpan.of(
                start_byte=0,
                end_byte=10,
                start_line=5,
                start_column=0,
                end_line=2,
                end_column=0,
            )

    def test_the_factory_is_keyword_only(self) -> None:
        """Six integers in a row are trivially transposable.

        A transposed span passes any validation that only checks ordering, so the
        factory refuses positional arguments outright.
        """
        with pytest.raises(TypeError):
            SourceSpan.of(0, 5, 0, 0, 0, 5)  # type: ignore[misc]

    def test_empty_at_builds_a_zero_width_span(self) -> None:
        """A convenience for the missing-node case."""
        position = SourcePosition(byte=3, line=0, column=3)
        assert SourceSpan.empty_at(position).is_empty is True

    def test_is_immutable(self) -> None:
        """A span cannot be edited after construction."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            span(0, 5).start = SourcePosition(byte=1, line=0, column=1)  # type: ignore[misc]


class TestSourceSpanMeasures:
    """Derived sizes."""

    def test_byte_length(self) -> None:
        """Length is the half-open difference."""
        assert span(4, 11).byte_length == 7

    def test_line_count_is_at_least_one(self) -> None:
        """A span on one line touches one line, not zero."""
        assert span(0, 5).line_count == 1
        multi = SourceSpan.of(
            start_byte=0,
            end_byte=30,
            start_line=0,
            start_column=0,
            end_line=2,
            end_column=0,
        )
        assert multi.line_count == 3

    def test_single_line_detection(self) -> None:
        """Whether a span begins and ends on one line."""
        assert span(0, 5).is_single_line is True
        multi = SourceSpan.of(
            start_byte=0,
            end_byte=30,
            start_line=0,
            start_column=0,
            end_line=1,
            end_column=5,
        )
        assert multi.is_single_line is False


class TestSourceSpanRelations:
    """Containment and overlap."""

    def test_containment(self) -> None:
        """Containment is the relation extraction uses to nest declarations.

        A method is the declaration whose span its class's span contains, which is how
        nesting is observed without any resolution.
        """
        outer = span(0, 20)
        inner = span(4, 8)
        assert outer.contains(inner) is True
        assert inner.contains(outer) is False

    def test_a_span_contains_itself(self) -> None:
        """Containment is reflexive, so a declaration's own name span qualifies."""
        assert span(0, 5).contains(span(0, 5)) is True

    def test_contains_byte_is_half_open(self) -> None:
        """The end byte is excluded, matching Python slicing."""
        subject = span(4, 8)
        assert subject.contains_byte(4) is True
        assert subject.contains_byte(7) is True
        assert subject.contains_byte(8) is False
        assert subject.contains_byte(3) is False

    def test_adjacent_spans_do_not_overlap(self) -> None:
        """Half-open ranges that touch share no byte.

        If adjacency counted as overlap, every sibling node in a tree would appear to
        conflict with its neighbour.
        """
        assert span(0, 5).overlaps(span(5, 10)) is False

    def test_partially_overlapping_spans_overlap(self) -> None:
        """Sharing one byte is overlap."""
        assert span(0, 6).overlaps(span(5, 10)) is True

    def test_an_empty_span_overlaps_nothing(self) -> None:
        """A span with no bytes has none to share."""
        assert span(5, 5).overlaps(span(0, 10)) is False
        assert span(0, 10).overlaps(span(5, 5)) is False


class TestSourceSpanExtraction:
    """Reading text through a span."""

    def test_slice_matches_python_slicing(self) -> None:
        """The half-open range needs no adjustment at the call site.

        A closed range would require every caller to add one, and every caller that
        forgot would truncate the last byte of every identifier.
        """
        subject = span(4, 11)
        assert subject.slice_of(SOURCE) == b"handler"
        assert subject.slice_of(SOURCE) == SOURCE[4:11]

    def test_text_decodes(self) -> None:
        """Text extraction decodes the sliced bytes."""
        assert span(4, 11).text_of(SOURCE) == "handler"

    def test_text_replaces_undecodable_bytes(self) -> None:
        """A mixed-encoding file must not abort a build.

        SDD section 3 (L2 failure modes) requires that one bad file not fail a build, so
        decoding replaces rather than raises; the bytes remain available for fidelity.
        """
        raw = b"name = '\xff\xfe'"
        text = SourceSpan.of(
            start_byte=0,
            end_byte=len(raw),
            start_line=0,
            start_column=0,
            end_line=0,
            end_column=len(raw),
        ).text_of(raw)
        assert "\ufffd" in text

    def test_slicing_past_the_source_is_rejected(self) -> None:
        """A span longer than its content describes a different file.

        Returning a short slice would silently produce a wrong identifier; raising says
        the span and the bytes disagree.
        """
        with pytest.raises(ValueError, match="does not describe this content"):
            span(0, 500).slice_of(SOURCE)

    def test_an_empty_span_slices_to_nothing(self) -> None:
        """A zero-width span yields empty bytes rather than raising."""
        assert span(5, 5).slice_of(SOURCE) == b""


class TestSourceSpanOrdering:
    """Deterministic sort order."""

    def test_containers_sort_before_their_contents(self) -> None:
        """Start ascending, then end descending.

        A class must sort before the methods inside it, so a single pass over sorted
        declarations can maintain a container stack.
        """
        outer = span(0, 100)
        inner = span(0, 10)
        assert outer.sort_key() < inner.sort_key()

    def test_earlier_spans_sort_first(self) -> None:
        """Position dominates the ordering."""
        assert span(0, 5).sort_key() < span(6, 9).sort_key()

    def test_sorting_is_stable_across_runs(self) -> None:
        """The key is a tuple of integers, so ordering cannot vary between processes.

        A non-deterministic order would change the tree digest on identical input and
        break the response caching of SDD section 5.5.
        """
        spans = [span(6, 9), span(0, 100), span(0, 10)]
        assert [
            item.sort_key() for item in sorted(spans, key=lambda s: s.sort_key())
        ] == [
            (0, -100),
            (0, -10),
            (6, -9),
        ]
