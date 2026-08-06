"""Syntactic fact extractors for supported languages."""

from __future__ import annotations

from ria.infrastructure.parser.extractors.js_ts_extractor import JsTsSyntaxExtractor
from ria.infrastructure.parser.extractors.python_extractor import PythonSyntaxExtractor

__all__ = ["PythonSyntaxExtractor", "JsTsSyntaxExtractor"]
