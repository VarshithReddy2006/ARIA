"""Default language plugin implementation.

Binds together a :class:`~ria.domain.models.language_plugin.LanguagePluginDescriptor`, a
:class:`~ria.ports.parser.ParserPort`, and an optional
:class:`~ria.ports.parser.SyntaxExtractorPort`. Performs parsing, timing measurement,
extraction, diagnostic collection, and statistics generation to produce a complete
:class:`~ria.domain.models.parse_result.ParseResult`.
"""

from __future__ import annotations

import time
from typing import FrozenSet, Optional

from ria.domain.enums import DiagnosticSeverity, ParserCapability
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.language_plugin import LanguagePluginDescriptor
from ria.domain.models.parse_result import (
    ParseDiagnostic,
    ParseResult,
    ParseStatistics,
    ParseTiming,
)
from ria.domain.models.parser_identity import ParserFingerprint
from ria.domain.models.syntax_facts import ExtractedSyntax
from ria.ports.parser import LanguagePluginPort, ParserPort, SyntaxExtractorPort

__all__ = ["DefaultLanguagePlugin"]


class DefaultLanguagePlugin(LanguagePluginPort):
    """Standard LanguagePluginPort implementation binding parser and extractor.

    Attributes:
        descriptor: Language plugin metadata and declared capabilities.
        parser: Parser adapter used to generate syntax trees.
        extractor: Extractor port used to extract declarations, imports, etc.
    """

    def __init__(
        self,
        descriptor: LanguagePluginDescriptor,
        parser: ParserPort,
        extractor: Optional[SyntaxExtractorPort] = None,
    ) -> None:
        self._descriptor = descriptor
        self._parser = parser
        self._extractor = extractor

    @property
    def descriptor(self) -> LanguagePluginDescriptor:
        """Language plugin descriptor."""
        return self._descriptor

    def fingerprint(self) -> ParserFingerprint:
        """Return the ParserFingerprint of results produced by this plugin."""
        return self._descriptor.fingerprint

    def parse(
        self,
        unit: FileUnit,
        source_bytes: bytes,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> ParseResult:
        """Parse source bytes and extract syntactic facts into a ParseResult.

        Performs timing measurements, collects error diagnostics, measures statistics,
        and ensures that a parse failure yields a result with diagnostics rather than
        raising an uncaught exception.

        Args:
            unit: File unit describing path, content hash, and language.
            source_bytes: File content bytes.
            timeout_seconds: Optional parse timeout.

        Returns:
            ParseResult value object.
        """
        diagnostics = []
        parse_start = time.perf_counter()

        # Step 1: Parse bytes into SyntaxTree
        tree = None
        try:
            tree = self._parser.parse_bytes(
                source_bytes,
                language=unit.language,
                content_hash=unit.content_hash,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            diagnostics.append(
                ParseDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message=f"parsing failed: {exc}",
                )
            )

        parse_seconds = time.perf_counter() - parse_start

        # Record warnings for syntax error nodes inside the tree
        if tree is not None and tree.has_errors:
            for err_node in tree.error_nodes:
                kind_str = "missing node" if err_node.is_missing else "syntax error"
                diagnostics.append(
                    ParseDiagnostic(
                        severity=DiagnosticSeverity.WARNING,
                        message=f"{kind_str} at offset {err_node.span.start.byte}",
                        span=err_node.span,
                        node_kind=err_node.kind,
                    )
                )

        # Step 2: Extract syntax facts if tree exists and extractor is present
        extracted = ExtractedSyntax()
        extract_seconds = 0.0

        if tree is not None and self._extractor is not None:
            extract_start = time.perf_counter()
            try:
                extracted = self._extractor.extract(tree, source_bytes)
            except Exception as exc:
                diagnostics.append(
                    ParseDiagnostic(
                        severity=DiagnosticSeverity.WARNING,
                        message=f"syntax extraction incomplete: {exc}",
                    )
                )
            extract_seconds = time.perf_counter() - extract_start

        timing = ParseTiming(
            parse_seconds=parse_seconds,
            extract_seconds=extract_seconds,
        )

        statistics = (
            ParseStatistics.of(tree, extracted)
            if tree is not None
            else ParseStatistics(source_bytes=len(source_bytes))
        )

        # If no tree was produced and no diagnostics were recorded, add fallback diagnostic
        if tree is None and not diagnostics:
            diagnostics.append(
                ParseDiagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    message="unable to parse file content",
                )
            )

        capabilities: FrozenSet[ParserCapability] = self._descriptor.capabilities

        return ParseResult(
            reuse_key=unit.reuse_key,
            language=unit.language,
            fingerprint=self.fingerprint(),
            tree=tree,
            extracted=extracted,
            diagnostics=tuple(diagnostics),
            timing=timing,
            statistics=statistics,
            capabilities=capabilities,
            from_cache=False,
        )
