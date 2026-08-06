"""Parse result and its diagnostics, timing and statistics.

The artefact Milestone 3 produces and Milestone 4 consumes. It carries the tree, the
extracted syntax, everything that went wrong, and the component versions that produced
it.

Why the versions travel with the result
---------------------------------------
A cached result may have been produced months earlier. Without the fingerprint embedded,
a consumer holding a result cannot tell which grammar or extractor produced it, and a
precision investigation has nowhere to start. This is the same reasoning that puts a
provenance triple on every relation in Twin Spec section 3.2: an observation whose
producer is unknown cannot be trusted or corrected.

Why a parse failure is a result and not an exception
---------------------------------------------------
SDD section 3 (L2 failure modes) requires that a syntax error yield whatever parsed with
the error recorded, because "one bad file must not fail a build". A result therefore
always exists; ``diagnostics`` and ``status`` describe how much of it to trust. Only a
fault that prevents producing any result at all — a missing plugin, unreadable content —
raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Optional, Tuple

from ria.domain.enums import (
    DiagnosticSeverity,
    ParseStatus,
    ParserCapability,
)
from ria.domain.models.parser_identity import ParserFingerprint
from ria.domain.models.span import SourceSpan
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.domain.models.syntax_tree import SyntaxTree

__all__ = ["ParseDiagnostic", "ParseTiming", "ParseStatistics", "ParseResult"]


@dataclass(frozen=True)
class ParseDiagnostic:
    """One problem observed while parsing or extracting.

    Attributes:
        severity: How much of the file the problem invalidates.
        message: Human-readable description. Never contains file content, because
            diagnostics are logged and a message carrying source could leak a secret
            from a file that happens not to parse.
        span: Where the problem is, when it has a location. ``None`` for a
            file-scoped problem such as a parser timeout.
        node_kind: Grammar node type involved, when the problem concerns one. Lets a
            plugin author find the offending grammar rule without re-parsing.
    """

    severity: DiagnosticSeverity
    message: str
    span: Optional[SourceSpan] = None
    node_kind: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.message or not self.message.strip():
            raise ValueError("a diagnostic must carry a message")
        if self.node_kind is not None and not self.node_kind:
            raise ValueError("node_kind must be non-empty when present")

    @property
    def is_located(self) -> bool:
        """Whether the diagnostic points at a position in the file."""
        return self.span is not None

    def sort_key(self) -> Tuple[int, int, str]:
        """Deterministic ordering: located problems by position, then unlocated ones.

        Unlocated diagnostics sort last rather than first, so a reader sees the specific
        problems before the file-wide ones.
        """
        if self.span is None:
            return (1, 0, self.message)
        return (0, self.span.start.byte, self.message)

    def __str__(self) -> str:
        location = f" at {self.span}" if self.span else ""
        return f"[{self.severity}]{location} {self.message}"


@dataclass(frozen=True)
class ParseTiming:
    """How long each phase of one parse took.

    Recorded per phase rather than as one total because the phases have different causes
    of slowness: a slow parse indicates a pathological file or grammar, a slow extraction
    indicates an inefficient query. One number would leave an investigation with nowhere
    to look.

    Attributes:
        parse_seconds: Time to produce the syntax tree.
        extract_seconds: Time to turn the tree into extracted syntax.
    """

    parse_seconds: float = 0.0
    extract_seconds: float = 0.0

    def __post_init__(self) -> None:
        for name in ("parse_seconds", "extract_seconds"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")

    @property
    def total_seconds(self) -> float:
        """Total time across both phases."""
        return self.parse_seconds + self.extract_seconds

    def __str__(self) -> str:
        return f"parse={self.parse_seconds:.4f}s extract={self.extract_seconds:.4f}s"


@dataclass(frozen=True)
class ParseStatistics:
    """Size measures of one parse.

    Attributes:
        source_bytes: Bytes parsed.
        node_count: Nodes in the tree.
        max_depth: Depth of the tree.
        error_node_count: Nodes the parser flagged as errors or missing.
        declaration_count: Declarations extracted.
        import_count: Import statements extracted.
        export_count: Export statements extracted.
        comment_count: Free-standing comments extracted.
    """

    source_bytes: int = 0
    node_count: int = 0
    max_depth: int = 0
    error_node_count: int = 0
    declaration_count: int = 0
    import_count: int = 0
    export_count: int = 0
    comment_count: int = 0

    def __post_init__(self) -> None:
        for name in (
            "source_bytes",
            "node_count",
            "max_depth",
            "error_node_count",
            "declaration_count",
            "import_count",
            "export_count",
            "comment_count",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value}")
        if self.error_node_count > self.node_count:
            raise ValueError(
                f"error_node_count ({self.error_node_count}) cannot exceed "
                f"node_count ({self.node_count})"
            )

    @classmethod
    def of(cls, tree: SyntaxTree, extracted: ExtractedSyntax) -> "ParseStatistics":
        """Measure a tree and its extraction.

        Derived rather than accumulated during parsing, so the statistics cannot drift
        out of step with the artefacts they describe.

        Args:
            tree: The syntax tree.
            extracted: The extracted syntax.
        """
        return cls(
            source_bytes=tree.source_bytes,
            node_count=tree.node_count,
            max_depth=tree.max_depth,
            error_node_count=len(tree.error_nodes),
            declaration_count=len(extracted.declarations),
            import_count=len(extracted.imports),
            export_count=len(extracted.exports),
            comment_count=len(extracted.comments),
        )

    @property
    def error_node_ratio(self) -> float:
        """Fraction of nodes the parser could not fit into the grammar.

        The measure of how much of a file is untrustworthy. Zero for an empty tree, since
        a file with no nodes has no bad ones.
        """
        if self.node_count == 0:
            return 0.0
        return self.error_node_count / self.node_count

    def __str__(self) -> str:
        return (
            f"{self.node_count} nodes, {self.declaration_count} declarations, "
            f"{self.error_node_count} errors"
        )


@dataclass(frozen=True)
class ParseResult:
    """Everything one parse produced for one file.

    Attributes:
        reuse_key: The file unit's content-and-language reuse key the result belongs to.
            Present so a result read from a cache can be verified against the unit it is
            about to be used for, rather than trusted because the lookup returned it.
        language: Canonical language name the file was parsed as.
        fingerprint: Component versions that produced this result.
        tree: The syntax tree, or ``None`` when no tree could be produced.
        extracted: Extracted syntax. Empty when there is no tree, or when the plugin
            declares no extraction capability.
        diagnostics: Everything that went wrong, in deterministic order.
        timing: Per-phase durations.
        statistics: Size measures.
        capabilities: Capabilities the producing plugin declared. Carried on the result
            so a consumer can distinguish "this file has no classes" from "this plugin
            cannot find classes" — two situations with identical output and opposite
            meanings.
        from_cache: Whether the result was served from cache rather than parsed. Never
            part of equality: a cached result and a freshly parsed one describing the
            same content must compare equal, or the cache could not be verified against
            a fresh parse in a test.
    """

    reuse_key: str
    language: str
    fingerprint: ParserFingerprint
    tree: Optional[SyntaxTree] = None
    extracted: ExtractedSyntax = field(default_factory=ExtractedSyntax)
    diagnostics: Tuple[ParseDiagnostic, ...] = ()
    timing: ParseTiming = field(default_factory=ParseTiming)
    statistics: ParseStatistics = field(default_factory=ParseStatistics)
    capabilities: FrozenSet[ParserCapability] = frozenset()
    from_cache: bool = field(default=False, compare=False)

    def __post_init__(self) -> None:
        if not self.reuse_key:
            raise ValueError("reuse_key must be non-empty")
        if not self.language:
            raise ValueError("language must be non-empty")
        if self.tree is not None and self.tree.language != self.language:
            raise ValueError(
                f"result language {self.language!r} disagrees with tree language "
                f"{self.tree.language!r}"
            )
        if self.tree is None and not self.extracted.is_empty:
            raise ValueError(
                "extracted syntax cannot exist without a tree to have extracted it from"
            )
        if self.tree is None and not self.diagnostics:
            raise ValueError(
                "a result with no tree must record why none could be produced"
            )
        object.__setattr__(
            self,
            "diagnostics",
            tuple(sorted(self.diagnostics, key=lambda item: item.sort_key())),
        )
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))

    # -- status ------------------------------------------------------------

    @property
    def status(self) -> ParseStatus:
        """The file unit parse status this result implies.

        Maps onto the existing :class:`~ria.domain.enums.ParseStatus` rather than
        introducing a parallel vocabulary, so the coverage report of Twin Spec section 9
        reads one enum. ``PARTIAL`` is the honest value for a file that parsed with
        errors: some declarations were found and some were not, and reporting either
        ``PARSED`` or ``UNPARSEABLE`` would overstate one side.
        """
        if self.tree is None:
            return ParseStatus.UNPARSEABLE
        if self.tree.truncated or self.tree.has_errors:
            return ParseStatus.PARTIAL
        return ParseStatus.PARSED

    @property
    def status_reason(self) -> Optional[str]:
        """Why the status is not a clean parse, or ``None`` when it is.

        Satisfies the invariant that
        :class:`~ria.domain.models.file_unit.FileUnit` enforces: a unit whose status is
        ``UNPARSEABLE`` or ``SKIPPED`` must state a cause, so a coverage gap always has
        an explanation.
        """
        if self.status is ParseStatus.PARSED:
            return None
        blocking = [
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.severity.degrades_coverage
        ]
        if blocking:
            return blocking[0].message
        if self.tree is not None and self.tree.truncated:
            return "parsing stopped before the end of the file"
        return "the file did not parse completely"

    @property
    def is_usable(self) -> bool:
        """Whether the result carries a tree a consumer can walk."""
        return self.tree is not None

    @property
    def has_errors(self) -> bool:
        """Whether any diagnostic reduces confidence in the result."""
        return any(
            diagnostic.severity.degrades_coverage for diagnostic in self.diagnostics
        )

    # -- capabilities ------------------------------------------------------

    def supports(self, capability: ParserCapability) -> bool:
        """Whether the producing plugin declared a capability.

        Args:
            capability: Capability to test.
        """
        return capability in self.capabilities

    def diagnostics_of(
        self, severity: DiagnosticSeverity
    ) -> Tuple[ParseDiagnostic, ...]:
        """Diagnostics of one severity, in deterministic order.

        Args:
            severity: Severity to filter by.
        """
        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.severity is severity
        )

    # -- derived reports ---------------------------------------------------

    def metric_labels(self) -> Mapping[str, str]:
        """Bounded-cardinality labels describing this result.

        Excludes the reuse key and the fingerprint token: both are unbounded, and a
        metric labelled with either would create one series per file or per version.
        """
        return {
            "language": self.language,
            "status": self.status.value,
            "cached": "true" if self.from_cache else "false",
        }

    def as_cached(self) -> "ParseResult":
        """Return this result marked as served from cache.

        A copy rather than a mutation, because a result is immutable and the cache must
        not alter the artefact it stored. ``from_cache`` is excluded from equality, so
        the copy compares equal to the original.
        """
        if self.from_cache:
            return self
        return ParseResult(
            reuse_key=self.reuse_key,
            language=self.language,
            fingerprint=self.fingerprint,
            tree=self.tree,
            extracted=self.extracted,
            diagnostics=self.diagnostics,
            timing=self.timing,
            statistics=self.statistics,
            capabilities=self.capabilities,
            from_cache=True,
        )

    def __str__(self) -> str:
        source = "cached" if self.from_cache else "parsed"
        return f"parse({self.language}, {self.status}, {self.statistics}, {source})"
