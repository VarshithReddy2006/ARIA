"""Tests for ParseCacheEntry."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import (
    ComponentVersion,
    ParseCacheKey,
    ParserFingerprint,
)
from ria.domain.models.span import SourceSpan
from ria.domain.models.syntax_tree import SyntaxNode, SyntaxTree

CONTENT_HASH = "sha256:" + "a" * 64
REUSE_KEY = f"{CONTENT_HASH}|python"


def span(start: int = 0, end: int = 10) -> SourceSpan:
    return SourceSpan.of(
        start_byte=start,
        end_byte=end,
        start_line=0,
        start_column=start,
        end_line=0,
        end_column=end,
    )


def make_fingerprint(ver: str = "1.0.0") -> ParserFingerprint:
    return ParserFingerprint(
        parser=ComponentVersion("tree-sitter-python", "0.21.0"),
        extractor=ComponentVersion("python-extractor", ver),
        language=ComponentVersion("python-plugin", "1.0.0"),
    )


def make_tree(language: str = "python") -> SyntaxTree:
    return SyntaxTree(
        language=language,
        root=SyntaxNode(kind="module", span=span(0, 10)),
        content_hash=CONTENT_HASH,
        source_bytes=10,
    )


class TestParseCacheEntry:
    def test_valid_cache_entry(self) -> None:
        fp = make_fingerprint("1.0.0")
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fp)
        res = ParseResult(
            reuse_key=REUSE_KEY,
            language="python",
            fingerprint=fp,
            tree=make_tree("python"),
        )
        now = datetime.now(timezone.utc)

        entry = ParseCacheEntry(key=key, result=res, cached_at=now)
        assert entry.key == key
        assert entry.result == res
        assert entry.cached_at == now
        assert entry.matches_fingerprint(fp)
        assert not entry.matches_fingerprint(make_fingerprint("2.0.0"))

        cached_res = entry.as_result()
        assert cached_res.from_cache is True
        assert cached_res.reuse_key == REUSE_KEY

    def test_mismatched_reuse_key_raises(self) -> None:
        fp = make_fingerprint()
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fp)
        res = ParseResult(
            reuse_key=f"{CONTENT_HASH}|java",
            language="java",
            fingerprint=fp,
            tree=make_tree("java"),
        )
        now = datetime.now(timezone.utc)

        with pytest.raises(ValueError, match="disagrees with parse result reuse_key"):
            ParseCacheEntry(key=key, result=res, cached_at=now)

    def test_mismatched_fingerprint_raises(self) -> None:
        fp1 = make_fingerprint("1.0.0")
        fp2 = make_fingerprint("2.0.0")
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fp1)
        res = ParseResult(
            reuse_key=REUSE_KEY,
            language="python",
            fingerprint=fp2,
            tree=make_tree("python"),
        )
        now = datetime.now(timezone.utc)

        with pytest.raises(ValueError, match="disagrees with parse result fingerprint"):
            ParseCacheEntry(key=key, result=res, cached_at=now)

    def test_naive_datetime_raises(self) -> None:
        fp = make_fingerprint()
        key = ParseCacheKey(reuse_key=REUSE_KEY, fingerprint=fp)
        res = ParseResult(
            reuse_key=REUSE_KEY,
            language="python",
            fingerprint=fp,
            tree=make_tree("python"),
        )
        naive_now = datetime.now()  # no tz info

        with pytest.raises(
            ValueError, match="cached_at datetime must be timezone-aware"
        ):
            ParseCacheEntry(key=key, result=res, cached_at=naive_now)
