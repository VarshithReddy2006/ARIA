"""Tests for declarations, syntax facts, parser identity and parse results.

Two themes run through this module. First, that the syntax layer records observations and
never conclusions — no resolved paths, no monikers, no confidence — because the foundation
documents identify name-matched edges presented as bindings as the previous architecture's
central defect. Second, that the cache key invalidates exactly as widely as the change
that caused it.
"""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.enums import (
    DeclarationKind,
    DiagnosticSeverity,
    ParseStatus,
    ParserCapability,
    Visibility,
)
from ria.domain.models.declaration import Annotation, DocComment, SyntaxDeclaration
from ria.domain.models.parse_result import (
    ParseDiagnostic,
    ParseResult,
    ParseStatistics,
    ParseTiming,
)
from ria.domain.models.parser_identity import (
    ComponentVersion,
    ParseCacheKey,
    ParserFingerprint,
)
from ria.domain.models.span import SourceSpan
from ria.domain.models.syntax_facts import (
    CommentBlock,
    ExportStatement,
    ExtractedSyntax,
    ImportedName,
    ImportStatement,
)
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree

CONTENT_HASH = "sha256:" + "a" * 64
REUSE_KEY = f"{CONTENT_HASH}|python"


def span(start: int, end: int) -> SourceSpan:
    """Build a single-line span."""
    return SourceSpan.of(
        start_byte=start,
        end_byte=end,
        start_line=0,
        start_column=start,
        end_line=0,
        end_column=end,
    )


def fingerprint(**overrides) -> ParserFingerprint:
    """Build a parser fingerprint, overriding one component at a time."""
    components = {
        "parser": ComponentVersion(name="tree-sitter-python", version="0.21.0"),
        "extractor": ComponentVersion(name="python-extractor", version="1.0.0"),
        "language": ComponentVersion(name="python-plugin", version="1.0.0"),
    }
    components.update(overrides)
    return ParserFingerprint(**components)


def declaration(**overrides) -> SyntaxDeclaration:
    """Build a declaration with sensible defaults."""
    defaults = dict(
        kind=DeclarationKind.FUNCTION,
        name="handler",
        span=span(0, 30),
        name_span=span(4, 11),
        node_kind="function_definition",
    )
    defaults.update(overrides)
    return SyntaxDeclaration(**defaults)


def tree() -> SyntaxTree:
    """Build a minimal valid tree."""
    return SyntaxTree(
        language="python",
        root=SyntaxNode(kind="module", span=span(0, 30)),
        content_hash=CONTENT_HASH,
        source_bytes=30,
    )


class TestAnnotation:
    """Decorators and annotations."""

    def test_records_the_name_and_raw_arguments(self) -> None:
        """Arguments are captured as text, not parsed values.

        Interpreting ``@app.get("/users")`` as a route requires framework knowledge,
        which is a Milestone 4 concern; keeping the text means that concern has something
        to work from without the parser having pretended to understand it.
        """
        subject = Annotation(
            name="app.get", span=span(0, 18), arguments_text='("/users")'
        )
        assert subject.name == "app.get"
        assert subject.has_arguments is True
        assert str(subject) == '@app.get("/users")'

    def test_absent_and_empty_arguments_are_distinguishable(self) -> None:
        """No argument list and an empty one are different observations."""
        assert Annotation(name="staticmethod", span=span(0, 13)).has_arguments is False
        assert (
            Annotation(name="f", span=span(0, 3), arguments_text="()").has_arguments
            is True
        )

    def test_rejects_an_empty_name(self) -> None:
        """An annotation without a name cannot be matched by a descriptor."""
        with pytest.raises(ValueError, match="name"):
            Annotation(name="", span=span(0, 1))


class TestDocComment:
    """Attached documentation."""

    def test_strips_surrounding_whitespace(self) -> None:
        """Documentation is normalised once, at construction."""
        assert (
            DocComment(text="  Does a thing.  ", span=span(0, 20)).text
            == "Does a thing."
        )

    def test_summary_is_the_first_paragraph(self) -> None:
        """Split on a blank line rather than a sentence boundary.

        Sentence splitting is language-dependent and would be wrong for the many
        docstrings that are not prose.
        """
        subject = DocComment(
            text="Saves the record.\n\nArgs:\n    value: thing.", span=span(0, 40)
        )
        assert subject.summary == "Saves the record."

    def test_summary_of_empty_documentation_is_empty(self) -> None:
        """An empty docstring yields an empty summary rather than raising."""
        subject = DocComment(text="   ", span=span(0, 3))
        assert subject.is_empty is True
        assert subject.summary == ""

    def test_leading_and_trailing_are_distinguishable(self) -> None:
        """Position is the only way to tell documentation from an orphaned comment."""
        assert DocComment(text="x", span=span(0, 1)).is_leading is True
        assert (
            DocComment(text="x", span=span(0, 1), is_leading=False).is_leading is False
        )


class TestSyntaxDeclaration:
    """The central syntactic observation."""

    def test_accepts_a_well_formed_declaration(self) -> None:
        """A declaration is a kind, a name, a span and a name span."""
        subject = declaration()
        assert subject.is_top_level is True
        assert subject.qualified_name == "handler"

    def test_rejects_an_empty_name(self) -> None:
        """An anonymous form is not a declaration."""
        with pytest.raises(ValueError, match="name"):
            declaration(name="")

    def test_rejects_a_missing_node_kind(self) -> None:
        """The originating grammar rule is retained for plugin debugging."""
        with pytest.raises(ValueError, match="node_kind"):
            declaration(node_kind="")

    def test_the_name_span_must_lie_inside_the_declaration(self) -> None:
        """A name outside its own declaration is a mis-extraction.

        Accepting it would produce a citation pointing at an unrelated part of the file,
        which is worse than no citation because it manufactures false confidence.
        """
        with pytest.raises(ValueError, match="outside its declaration span"):
            declaration(span=span(0, 10), name_span=span(20, 25))

    def test_rejects_an_empty_container_path_entry(self) -> None:
        """A blank container name would corrupt every lexical path built from it."""
        with pytest.raises(ValueError, match="container_path"):
            declaration(container_path=("Repo", ""))

    def test_lexical_path_appends_the_declaration_name(self) -> None:
        """The lexical address within the file, not a moniker.

        A moniker is scheme-qualified and globally stable (Twin Spec section 3.1);
        producing one requires knowing the module's identity, which is resolution.
        """
        subject = declaration(
            kind=DeclarationKind.METHOD, name="save", container_path=("Repository",)
        )
        assert subject.lexical_path == ("Repository", "save")
        assert subject.qualified_name == "Repository.save"
        assert subject.is_nested is True

    def test_visibility_defaults_to_not_applicable(self) -> None:
        """A language with no visibility concept says so rather than guessing public."""
        assert declaration().visibility is Visibility.NOT_APPLICABLE

    def test_inferred_visibility_is_not_explicit(self) -> None:
        """A convention-derived value is a weaker claim than a keyword.

        Conflating them would let Milestone 4's API surface classification treat a naming
        convention as a declaration.
        """
        subject = declaration(visibility=Visibility.INFERRED)
        assert subject.visibility.is_explicit is False
        assert declaration(visibility=Visibility.PUBLIC).visibility.is_explicit is True

    def test_annotation_helpers(self) -> None:
        """Annotation names are surfaced for framework entry-point detection."""
        subject = declaration(
            annotations=(
                Annotation(name="staticmethod", span=span(0, 13)),
                Annotation(name="app.get", span=span(0, 8), arguments_text="()"),
            )
        )
        assert subject.annotation_names == ("staticmethod", "app.get")
        assert subject.has_annotation("app.get") is True
        assert subject.has_annotation("absent") is False

    def test_modifier_helpers(self) -> None:
        """Grammar keywords are queryable."""
        subject = declaration(modifiers=("async", "static"))
        assert subject.has_modifier("async") is True
        assert subject.has_modifier("abstract") is False

    def test_collections_are_normalised_to_tuples(self) -> None:
        """A caller's list cannot mutate the declaration afterwards."""
        modifiers = ["async"]
        subject = declaration(modifiers=modifiers)
        modifiers.clear()
        assert subject.modifiers == ("async",)

    def test_sort_key_puts_containers_first_then_breaks_ties_by_name(self) -> None:
        """Position alone is not total, so the name completes the ordering.

        Two zero-width spans can coincide, and an unstable order would change serialised
        extraction output between runs on identical input.
        """
        outer = declaration(name="Outer", span=span(0, 100), name_span=span(6, 11))
        inner = declaration(name="inner", span=span(10, 40), name_span=span(14, 19))
        assert outer.sort_key() < inner.sort_key()

    def test_is_immutable(self) -> None:
        """A declaration cannot be edited after extraction."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            declaration().name = "other"  # type: ignore[misc]


class TestImportStatement:
    """Imports as written, never resolved."""

    def test_records_the_specifier_verbatim(self) -> None:
        """The module text is what the source says, not a path.

        Turning a specifier into a file requires the language's module resolution
        algorithm, which is Milestone 4's Resolution layer.
        """
        subject = ImportStatement(
            module_text="../utils/helpers",
            span=span(0, 30),
            node_kind="import_statement",
            is_relative=True,
        )
        assert subject.module_text == "../utils/helpers"
        assert subject.is_relative is True

    def test_local_names_apply_aliases(self) -> None:
        """The importing file sees the alias where one is present."""
        subject = ImportStatement(
            module_text="os.path",
            span=span(0, 30),
            node_kind="import_from_statement",
            names=(
                ImportedName(name="join"),
                ImportedName(name="dirname", alias="parent"),
            ),
        )
        assert subject.local_names == ("join", "parent")

    def test_wildcard_detection(self) -> None:
        """A star import is recognised from syntax."""
        subject = ImportStatement(
            module_text="os",
            span=span(0, 12),
            node_kind="import_from_statement",
            names=(ImportedName(name="*"),),
        )
        assert subject.has_wildcard is True
        assert subject.names[0].is_wildcard is True

    def test_a_side_effect_import_binds_nothing(self) -> None:
        """A contradiction between the flag and the names is rejected.

        A side-effect import cannot be dead-code eliminated, and recording names against
        it would make a later milestone report it as unused.
        """
        with pytest.raises(ValueError, match="binds no names"):
            ImportStatement(
                module_text="./polyfill",
                span=span(0, 20),
                node_kind="import_statement",
                names=(ImportedName(name="x"),),
                is_side_effect_only=True,
            )

    def test_type_only_imports_are_marked(self) -> None:
        """A type-only import is a real analysis dependency and no runtime dependency."""
        subject = ImportStatement(
            module_text="./types",
            span=span(0, 20),
            node_kind="import_statement",
            is_type_only=True,
        )
        assert subject.is_type_only is True

    def test_rejects_an_empty_specifier(self) -> None:
        """An import naming nothing cannot be resolved later."""
        with pytest.raises(ValueError, match="module_text"):
            ImportStatement(
                module_text="", span=span(0, 1), node_kind="import_statement"
            )

    def test_rejects_an_empty_imported_name(self) -> None:
        """A blank binding is not an observation."""
        with pytest.raises(ValueError):
            ImportedName(name="")

    def test_an_alias_must_be_non_empty_when_present(self) -> None:
        """An empty alias is absence, not a rename."""
        with pytest.raises(ValueError, match="alias"):
            ImportedName(name="join", alias="")


class TestExportStatement:
    """Exports as written."""

    def test_a_local_export_names_no_module(self) -> None:
        """A local export re-exports nothing."""
        subject = ExportStatement(
            span=span(0, 20),
            node_kind="export_statement",
            names=(ImportedName(name="handler"),),
        )
        assert subject.is_reexport is False

    def test_a_reexport_names_its_source(self) -> None:
        """A re-export carries the module it came from."""
        subject = ExportStatement(
            span=span(0, 30), node_kind="export_statement", module_text="./inner"
        )
        assert subject.is_reexport is True

    def test_a_wildcard_export_must_name_a_module(self) -> None:
        """``export *`` without a source is not a statement that can exist."""
        with pytest.raises(ValueError, match="must name the module"):
            ExportStatement(
                span=span(0, 10), node_kind="export_statement", is_wildcard=True
            )


class TestCommentBlock:
    """Free-standing comments."""

    def test_strips_and_records(self) -> None:
        """Text is normalised at construction."""
        subject = CommentBlock(
            text="  HACK: works around upstream bug  ",
            span=span(0, 40),
            node_kind="comment",
        )
        assert subject.text == "HACK: works around upstream bug"
        assert subject.is_empty is False

    def test_an_empty_comment_is_representable(self) -> None:
        """A bare delimiter is a comment with no content."""
        assert (
            CommentBlock(text="", span=span(0, 2), node_kind="comment").is_empty is True
        )

    def test_block_and_line_comments_are_distinguishable(self) -> None:
        """The delimiter style is recorded."""
        assert (
            CommentBlock(
                text="x", span=span(0, 5), node_kind="comment", is_block=True
            ).is_block
            is True
        )

    def test_rejects_a_missing_node_kind(self) -> None:
        """Provenance to the grammar rule is retained."""
        with pytest.raises(ValueError, match="node_kind"):
            CommentBlock(text="x", span=span(0, 1), node_kind="")


class TestExtractedSyntax:
    """The per-file collection of facts."""

    def test_sorts_every_collection_by_position(self) -> None:
        """Determinism covers extraction output, not only the tree.

        Sorting here means the invariant holds regardless of how a future plugin chooses
        to walk the tree.
        """
        first = declaration(name="a", span=span(0, 10), name_span=span(0, 1))
        second = declaration(name="b", span=span(20, 30), name_span=span(20, 21))
        subject = ExtractedSyntax(declarations=(second, first))
        assert [item.name for item in subject.declarations] == ["a", "b"]

    def test_empty_is_distinguishable_from_populated(self) -> None:
        """An empty extraction is recognisable."""
        assert ExtractedSyntax().is_empty is True
        assert ExtractedSyntax(declarations=(declaration(),)).is_empty is False

    def test_counts_omit_empty_categories(self) -> None:
        """Counts are usable directly as progress detail and metric labels."""
        subject = ExtractedSyntax(declarations=(declaration(),))
        assert subject.counts() == {"declarations": 1}
        assert subject.total == 1

    def test_declaration_kind_counts_feed_coverage(self) -> None:
        """Per-kind counts are what the coverage report of Twin Spec section 9 needs."""
        subject = ExtractedSyntax(
            declarations=(
                declaration(
                    kind=DeclarationKind.FUNCTION, name="a", name_span=span(0, 1)
                ),
                declaration(kind=DeclarationKind.CLASS, name="B", name_span=span(0, 1)),
            )
        )
        assert subject.declaration_kind_counts() == {"function": 1, "class": 1}

    def test_selection_helpers(self) -> None:
        """Declarations are selectable by kind and by container."""
        method = declaration(
            kind=DeclarationKind.METHOD,
            name="save",
            container_path=("Repo",),
            name_span=span(4, 8),
        )
        function = declaration(kind=DeclarationKind.FUNCTION, name="main")
        subject = ExtractedSyntax(declarations=(method, function))
        assert len(subject.declarations_of_kind(DeclarationKind.METHOD)) == 1
        assert [item.name for item in subject.top_level_declarations()] == ["main"]
        assert [item.name for item in subject.declarations_within(("Repo",))] == [
            "save"
        ]


class TestParserIdentity:
    """Component versions and the cache key."""

    def test_a_component_is_a_name_and_a_version(self) -> None:
        """Both are required to identify a producer."""
        assert str(ComponentVersion(name="tree-sitter-python", version="0.21.0")) == (
            "tree-sitter-python@0.21.0"
        )

    @pytest.mark.parametrize(
        "name,version",
        [
            ("", "1"),
            ("x", ""),
            ("has space", "1"),
            ("x", "1 2"),
            ("a:b", "1"),
            ("x", "a|b"),
        ],
    )
    def test_rejects_values_that_could_forge_a_separator(
        self, name: str, version: str
    ) -> None:
        """A version containing a separator could make two keys collide.

        A collision means one component's cached result is served for another's, which is
        the one failure a cache must never have.
        """
        with pytest.raises(ValueError):
            ComponentVersion(name=name, version=version)

    def test_the_fingerprint_token_has_a_fixed_component_order(self) -> None:
        """Order is fixed by the type, not by iteration.

        A site that composed components in a different order would produce a key that
        never hits and never errors — a cache that silently stops working while every
        test still passes.
        """
        token = fingerprint().token()
        assert token.index("tree-sitter-python") < token.index("python-extractor")
        assert token.index("python-extractor") < token.index("python-plugin")

    def test_the_fingerprint_digest_is_bounded_and_stable(self) -> None:
        """A bounded identifier is needed for filenames and metric labels."""
        assert len(fingerprint().digest()) == 16
        assert fingerprint().digest() == fingerprint().digest()

    @pytest.mark.parametrize("component", ["parser", "extractor", "language"])
    def test_changing_any_component_changes_the_key(self, component: str) -> None:
        """The milestone's cache rule: any component change invalidates.

        Three separate versions rather than one, so a Python extractor fix does not
        invalidate every cached Java parse.
        """
        original = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fingerprint())
        bumped = ParseCacheKey(
            reuse_key=REUSE_KEY,
            fingerprint=fingerprint(
                **{component: ComponentVersion(name="changed", version="2.0.0")}
            ),
        )
        assert bumped.digest() != original.digest()
        assert bumped.token() != original.token()

    def test_identical_inputs_produce_an_identical_key(self) -> None:
        """The same content and versions hit the same cache entry."""
        first = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fingerprint())
        second = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fingerprint())
        assert first == second
        assert first.digest() == second.digest()

    def test_different_content_produces_a_different_key(self) -> None:
        """Content is half the key."""
        other = ParseCacheKey(
            reuse_key=f"sha256:{'b' * 64}|python", fingerprint=fingerprint()
        )
        assert (
            other.digest()
            != ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fingerprint()).digest()
        )

    def test_the_same_content_in_two_languages_differs(self) -> None:
        """The reuse key carries the language, so TSX and TypeScript do not collide."""
        first = ParseCacheKey(
            reuse_key=f"{CONTENT_HASH}|typescript", fingerprint=fingerprint()
        )
        second = ParseCacheKey(
            reuse_key=f"{CONTENT_HASH}|tsx", fingerprint=fingerprint()
        )
        assert first.digest() != second.digest()

    def test_the_key_excludes_path_commit_and_repository(self) -> None:
        """Identical content elsewhere must be a cache hit.

        Including any location would make a file parsed again in another commit, branch
        or repository a miss, discarding the whole benefit of content addressing.
        """
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fingerprint())
        assert key.reuse_key == REUSE_KEY
        assert "commit" not in key.token()

    def test_with_fingerprint_substitutes_versions(self) -> None:
        """Lets a caller look for a result cached under previous versions.

        That is what makes a version bump an observable invalidation rather than a silent
        drop in hit rate.
        """
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fingerprint())
        older = key.with_fingerprint(
            fingerprint(
                extractor=ComponentVersion(name="python-extractor", version="0.9.0")
            )
        )
        assert older.reuse_key == key.reuse_key
        assert older.digest() != key.digest()

    def test_rejects_a_reuse_key_containing_the_separator(self) -> None:
        """A forged separator could make one key's token equal another's."""
        with pytest.raises(ValueError, match="separator"):
            ParseCacheKey(reuse_key="a\x1eb", fingerprint=fingerprint())

    def test_rejects_an_empty_reuse_key(self) -> None:
        """A key must identify content."""
        with pytest.raises(ValueError, match="reuse_key"):
            ParseCacheKey(reuse_key="", fingerprint=fingerprint())


class TestParseDiagnostic:
    """Problems observed while parsing."""

    def test_requires_a_message(self) -> None:
        """A diagnostic with no message gives an operator nothing to act on."""
        with pytest.raises(ValueError, match="message"):
            ParseDiagnostic(severity=DiagnosticSeverity.ERROR, message="   ")

    def test_a_location_is_optional(self) -> None:
        """A parser timeout concerns the whole file, not a position."""
        subject = ParseDiagnostic(
            severity=DiagnosticSeverity.ERROR, message="parser timed out"
        )
        assert subject.is_located is False

    def test_located_diagnostics_sort_before_unlocated_ones(self) -> None:
        """A reader sees specific problems before file-wide ones."""
        located = ParseDiagnostic(
            severity=DiagnosticSeverity.WARNING, message="syntax error", span=span(5, 6)
        )
        unlocated = ParseDiagnostic(
            severity=DiagnosticSeverity.ERROR, message="timed out"
        )
        assert located.sort_key() < unlocated.sort_key()

    def test_severity_determines_coverage_degradation(self) -> None:
        """Only warnings and errors mean extraction is incomplete."""
        assert DiagnosticSeverity.INFO.degrades_coverage is False
        assert DiagnosticSeverity.WARNING.degrades_coverage is True
        assert DiagnosticSeverity.ERROR.degrades_coverage is True


class TestParseTimingAndStatistics:
    """Per-phase durations and size measures."""

    def test_timing_sums_its_phases(self) -> None:
        """Phases are recorded separately because they have different causes of slowness."""
        subject = ParseTiming(parse_seconds=0.25, extract_seconds=0.75)
        assert subject.total_seconds == 1.0

    @pytest.mark.parametrize("field", ["parse_seconds", "extract_seconds"])
    def test_timing_rejects_a_negative_duration(self, field: str) -> None:
        """A negative duration would corrupt every aggregate computed from it."""
        with pytest.raises(ValueError, match=field):
            ParseTiming(**{field: -1.0})

    def test_statistics_are_derived_from_the_artefacts(self) -> None:
        """Measured rather than accumulated, so they cannot drift from what they describe."""
        extracted = ExtractedSyntax(declarations=(declaration(),))
        subject = ParseStatistics.of(tree(), extracted)
        assert subject.node_count == 1
        assert subject.declaration_count == 1
        assert subject.source_bytes == 30

    def test_error_ratio_of_an_empty_tree_is_zero(self) -> None:
        """A file with no nodes has no bad ones, rather than a division fault."""
        assert ParseStatistics().error_node_ratio == 0.0

    def test_error_ratio_measures_untrustworthiness(self) -> None:
        """The fraction of nodes the parser could not fit into the grammar."""
        subject = ParseStatistics(node_count=10, error_node_count=2)
        assert subject.error_node_ratio == 0.2

    def test_rejects_more_errors_than_nodes(self) -> None:
        """An impossible ratio is rejected at construction."""
        with pytest.raises(ValueError, match="cannot exceed"):
            ParseStatistics(node_count=1, error_node_count=2)

    @pytest.mark.parametrize(
        "field",
        [
            "source_bytes",
            "node_count",
            "max_depth",
            "declaration_count",
            "comment_count",
        ],
    )
    def test_rejects_negative_measures(self, field: str) -> None:
        """Counts are non-negative."""
        with pytest.raises(ValueError, match=field):
            ParseStatistics(**{field: -1})


class TestParseResult:
    """The artefact Milestone 4 consumes."""

    def make(self, **overrides) -> ParseResult:
        """Build a parse result with sensible defaults."""
        defaults = dict(
            reuse_key=REUSE_KEY,
            language="python",
            fingerprint=fingerprint(),
            tree=tree(),
            capabilities=frozenset(
                {ParserCapability.PARSE, ParserCapability.PRODUCE_AST}
            ),
        )
        defaults.update(overrides)
        return ParseResult(**defaults)

    def test_a_clean_parse_reports_parsed(self) -> None:
        """Status maps onto the existing file unit vocabulary."""
        subject = self.make()
        assert subject.status is ParseStatus.PARSED
        assert subject.status_reason is None
        assert subject.is_usable is True

    def test_a_tree_with_errors_reports_partial(self) -> None:
        """Partial is the honest value for a file that parsed with errors.

        Some declarations were found and some were not; reporting either ``PARSED`` or
        ``UNPARSEABLE`` would overstate one side.
        """
        root = SyntaxNode(
            kind="module",
            span=span(0, 30),
            children=(SyntaxNode(kind="ERROR", span=span(0, 2), is_error=True),),
        )
        broken = SyntaxTree(
            language="python", root=root, content_hash=CONTENT_HASH, source_bytes=30
        )
        subject = self.make(
            tree=broken,
            diagnostics=(
                ParseDiagnostic(
                    severity=DiagnosticSeverity.WARNING,
                    message="unexpected token",
                    span=span(0, 2),
                ),
            ),
        )
        assert subject.status is ParseStatus.PARTIAL
        assert subject.status_reason == "unexpected token"
        assert subject.has_errors is True

    def test_a_truncated_tree_reports_partial_with_a_reason(self) -> None:
        """A truncated parse states why even with no located diagnostic."""
        truncated = SyntaxTree(
            language="python",
            root=SyntaxNode(kind="module", span=span(0, 30)),
            content_hash=CONTENT_HASH,
            source_bytes=30,
            truncated=True,
        )
        subject = self.make(tree=truncated)
        assert subject.status is ParseStatus.PARTIAL
        assert "stopped before the end" in subject.status_reason

    def test_a_result_with_no_tree_reports_unparseable(self) -> None:
        """A parse failure is a result, not an exception.

        SDD section 3 (L2) requires that a bad file not fail a build, so the failure is
        described rather than raised.
        """
        subject = ParseResult(
            reuse_key=REUSE_KEY,
            language="python",
            fingerprint=fingerprint(),
            diagnostics=(
                ParseDiagnostic(
                    severity=DiagnosticSeverity.ERROR, message="no grammar installed"
                ),
            ),
        )
        assert subject.status is ParseStatus.UNPARSEABLE
        assert subject.status_reason == "no grammar installed"
        assert subject.is_usable is False

    def test_a_result_with_no_tree_must_say_why(self) -> None:
        """A coverage gap always states its cause, per PRD principle P11."""
        with pytest.raises(ValueError, match="must record why"):
            ParseResult(
                reuse_key=REUSE_KEY, language="python", fingerprint=fingerprint()
            )

    def test_extraction_cannot_exist_without_a_tree(self) -> None:
        """Declarations must have come from somewhere."""
        with pytest.raises(ValueError, match="without a tree"):
            ParseResult(
                reuse_key=REUSE_KEY,
                language="python",
                fingerprint=fingerprint(),
                extracted=ExtractedSyntax(declarations=(declaration(),)),
                diagnostics=(
                    ParseDiagnostic(severity=DiagnosticSeverity.ERROR, message="x"),
                ),
            )

    def test_the_result_language_must_match_the_tree(self) -> None:
        """A disagreement means the two artefacts describe different parses."""
        with pytest.raises(ValueError, match="disagrees with tree language"):
            self.make(language="typescript")

    def test_capabilities_travel_with_the_result(self) -> None:
        """A consumer can tell "no classes here" from "this plugin cannot find classes".

        The two produce identical output and mean opposite things, so the declaration has
        to be carried rather than inferred.
        """
        subject = self.make()
        assert subject.supports(ParserCapability.PARSE) is True
        assert subject.supports(ParserCapability.EXTRACT_CLASSES) is False

    def test_diagnostics_are_sorted_deterministically(self) -> None:
        """Order does not depend on the order problems were discovered."""
        subject = self.make(
            diagnostics=(
                ParseDiagnostic(
                    severity=DiagnosticSeverity.INFO, message="late", span=span(20, 21)
                ),
                ParseDiagnostic(
                    severity=DiagnosticSeverity.INFO, message="early", span=span(1, 2)
                ),
            )
        )
        assert [item.message for item in subject.diagnostics] == ["early", "late"]

    def test_diagnostics_can_be_filtered_by_severity(self) -> None:
        """Severity selection supports reporting."""
        subject = self.make(
            diagnostics=(
                ParseDiagnostic(severity=DiagnosticSeverity.INFO, message="note"),
                ParseDiagnostic(severity=DiagnosticSeverity.WARNING, message="warn"),
            )
        )
        assert len(subject.diagnostics_of(DiagnosticSeverity.WARNING)) == 1

    def test_as_cached_compares_equal_to_the_original(self) -> None:
        """The cache marker is excluded from equality.

        Otherwise a cached result could not be verified against a freshly parsed one in a
        test, which is the only way to prove the cache returns what parsing would.
        """
        fresh = self.make()
        cached = fresh.as_cached()
        assert cached == fresh
        assert cached.from_cache is True
        assert fresh.from_cache is False

    def test_as_cached_is_idempotent(self) -> None:
        """Marking an already-cached result returns it unchanged."""
        cached = self.make().as_cached()
        assert cached.as_cached() is cached

    def test_metric_labels_are_bounded(self) -> None:
        """Labels exclude the reuse key and the fingerprint.

        Both are unbounded, and a metric labelled with either would create one series per
        file or per version.
        """
        labels = self.make().metric_labels()
        assert set(labels) == {"language", "status", "cached"}

    def test_the_fingerprint_travels_with_the_result(self) -> None:
        """A cached result must say which versions produced it.

        A result whose producer is unknown cannot be trusted or corrected, which is the
        same reasoning that puts provenance on every relation in Twin Spec section 3.2.
        """
        assert self.make().fingerprint.parser.name == "tree-sitter-python"
