"""Deterministic Citation Verification Service (Recovery Item R-005).

Parses citation patterns from answers (file paths, line ranges), resolves them
against actual files on disk / symbol index / context snippets, validates line ranges,
and produces a deterministic CitationReport with citations_valid defaulting to False.
"""

from __future__ import annotations

import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Set
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Citation(BaseModel):
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    status: str = "unresolved"  # "verified" | "unresolved"
    reason: Optional[str] = None


class CitationReport(BaseModel):
    citations_valid: bool = False
    verified: List[Citation] = Field(default_factory=list)
    unresolved: List[Citation] = Field(default_factory=list)
    total_citations: int = 0
    feedback: str = ""


class CitationVerifier:
    """Deterministic citation verifier for codebase answers."""

    def __init__(self, repo_root: Optional[str] = None) -> None:
        self.repo_root = repo_root or os.getcwd()

    def verify_answer(
        self,
        answer: str,
        source_contexts: Optional[List[Any]] = None,
        repo_root: Optional[str] = None,
    ) -> CitationReport:
        """Deterministically parse and verify all citations in answer text.

        Args:
            answer: Generated response string containing citations.
            source_contexts: Optional context snippets used to construct answer.
            repo_root: Optional repository root path for file resolution.

        Returns:
            CitationReport with verified/unresolved citations and citations_valid flag.
        """
        root = repo_root or self.repo_root
        extracted = self.extract_citations(answer)

        if not extracted:
            return CitationReport(
                citations_valid=True,
                verified=[],
                unresolved=[],
                total_citations=0,
                feedback="No citations found in answer text.",
            )

        known_context_paths: Set[str] = set()
        if source_contexts:
            for src in source_contexts:
                if isinstance(src, dict):
                    meta = src.get("metadata", {})
                    path = meta.get("file_path") or meta.get("file") or meta.get("path")
                    if path:
                        known_context_paths.add(self._normalize_path(path))
                elif isinstance(src, str):
                    # Check string context for file paths
                    for m in re.findall(r"([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)", src):
                        known_context_paths.add(self._normalize_path(m))

        verified: List[Citation] = []
        unresolved: List[Citation] = []

        for raw_path, start_line, end_line in extracted:
            norm_path = self._normalize_path(raw_path)
            resolved_file_path = self._resolve_file_on_disk(norm_path, root)

            if resolved_file_path is None and norm_path not in known_context_paths:
                unresolved.append(
                    Citation(
                        file_path=raw_path,
                        start_line=start_line,
                        end_line=end_line,
                        status="unresolved",
                        reason=f"File path '{raw_path}' does not exist on disk or in retrieved context.",
                    )
                )
                continue

            # Check line numbers if disk file available
            if resolved_file_path and (start_line is not None or end_line is not None):
                line_ok, reason = self._verify_line_range(resolved_file_path, start_line, end_line)
                if not line_ok:
                    unresolved.append(
                        Citation(
                            file_path=raw_path,
                            start_line=start_line,
                            end_line=end_line,
                            status="unresolved",
                            reason=reason,
                        )
                    )
                    continue

            verified.append(
                Citation(
                    file_path=raw_path,
                    start_line=start_line,
                    end_line=end_line,
                    status="verified",
                    reason=None,
                )
            )

        total = len(extracted)
        # citations_valid is True if at least 0 unresolved citations exist and total > 0 (or no unresolved citations when total=0)
        citations_valid = (len(unresolved) == 0) if total > 0 else True

        feedback = (
            f"All {total} citation(s) verified successfully."
            if citations_valid
            else f"Verification failed: {len(unresolved)} of {total} citation(s) unresolved."
        )

        return CitationReport(
            citations_valid=citations_valid,
            verified=verified,
            unresolved=unresolved,
            total_citations=total,
            feedback=feedback,
        )

    def extract_citations(
        self, text: str
    ) -> List[Tuple[str, Optional[int], Optional[int]]]:
        """Extract (file_path, start_line, end_line) tuples from Markdown text."""
        citations: List[Tuple[str, Optional[int], Optional[int]]] = []
        seen: Set[Tuple[str, Optional[int], Optional[int]]] = set()

        # Pattern 1: **File:** path ... **Lines:** X-Y or X
        p1 = re.compile(
            r"\*\*File:\*\*\s*`?([^\n`*]+)`?(?:.*?\*\*Lines:\*\*\s*(\d+)(?:[–-]\s*(\d+))?)?",
            re.DOTALL | re.IGNORECASE,
        )
        for match in p1.finditer(text):
            path = match.group(1).strip()
            start = int(match.group(2)) if match.group(2) else None
            end = int(match.group(3)) if match.group(3) else start
            entry = (path, start, end)
            if entry not in seen:
                seen.add(entry)
                citations.append(entry)

        # Pattern 2: [path:LX-Y] or [path:X-Y] or [path](file:///...) or file:///path#LX-Y
        p2 = re.compile(
            r"\[([^\]:\n]+)(?::L?(\d+)(?:[–-]\s*(\d+))?)?\](?:\(file:///[^\)]+\))?",
            re.IGNORECASE,
        )
        for match in p2.finditer(text):
            path = match.group(1).strip()
            if "." in path or "/" in path or "\\" in path:
                start = int(match.group(2)) if match.group(2) else None
                end = int(match.group(3)) if match.group(3) else start
                entry = (path, start, end)
                if entry not in seen:
                    seen.add(entry)
                    citations.append(entry)

        # Pattern 3: explicit path:X-Y (e.g. backend/api.py:10-20 or nonexistent/file.py:1-5)
        p3 = re.compile(
            r"(?:^|\s|`)([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)(?:[–-]\s*(\d+))?",
            re.IGNORECASE,
        )
        for match in p3.finditer(text):
            path = match.group(1).strip()
            start = int(match.group(2)) if match.group(2) else None
            end = int(match.group(3)) if match.group(3) else start
            entry = (path, start, end)
            if entry not in seen:
                seen.add(entry)
                citations.append(entry)

        return citations

    def _normalize_path(self, raw_path: str) -> str:
        clean = raw_path.replace("\\", "/").strip()
        if clean.startswith("file:///"):
            clean = clean[8:]
        clean = clean.lstrip("/")
        return clean

    def _resolve_file_on_disk(self, norm_path: str, repo_root: str) -> Optional[str]:
        """Try resolving norm_path against repo_root or current working directory."""
        candidates = [
            os.path.join(repo_root, norm_path),
            os.path.join(os.getcwd(), norm_path),
            norm_path,
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        return None

    def _verify_line_range(
        self, abs_file_path: str, start_line: Optional[int], end_line: Optional[int]
    ) -> Tuple[bool, Optional[str]]:
        """Verify that line range fits within total lines of file."""
        try:
            with open(abs_file_path, "r", encoding="utf-8", errors="ignore") as f:
                total_lines = sum(1 for _ in f)

            if start_line is not None and start_line < 1:
                return False, f"Start line {start_line} is less than 1."
            if start_line is not None and start_line > total_lines:
                return (
                    False,
                    f"Start line {start_line} exceeds total file length ({total_lines} lines).",
                )
            if end_line is not None and end_line > total_lines:
                return (
                    False,
                    f"End line {end_line} exceeds total file length ({total_lines} lines).",
                )
            if (
                start_line is not None
                and end_line is not None
                and end_line < start_line
            ):
                return (
                    False,
                    f"End line {end_line} is less than start line {start_line}.",
                )

            return True, None
        except Exception as exc:
            return False, f"Could not read file for line verification: {exc}"
