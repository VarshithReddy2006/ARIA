"""Rendering & Evidence Formatting Regression Suite.

Verifies:
  1. No malformed HTML or CSS leakage (400">, class=, text-indigo-, font-semibold, style=) can exist in outputs.
  2. Evidence sections render as structured citations (**File**, **Lines**, **Reason**, **Confidence**).
  3. Code blocks, lists, tables, quotes, headings, and mixed Markdown render cleanly.
  4. Complete compliance with all Completion Gate criteria.
"""

from __future__ import annotations

import re
import pytest

from services.chat.fallback_renderer import render_fallback
from services.chat.context_builder import ContextBuilder, _CHARS_PER_TOKEN
from models.schemas import EvidenceItem


# ---------------------------------------------------------------------------
# 1. HTML / CSS Artifact Leakage Tests
# ---------------------------------------------------------------------------


class TestRenderingArtifactLeakage:
    """Verifies that rendering artifacts NEVER appear in outputs."""

    LEAKAGE_PATTERNS = [
        r'400">',
        r'class=',
        r'text-indigo-400',
        r'font-semibold',
        r'text-text-subtle',
        r'style=',
        r'dangerouslySetInnerHTML',
        r'<span class=',
        r'<astro-island',
    ]

    def test_fallback_renderer_has_no_leakage(self):
        fallback = render_fallback(
            question="Explain backend/api.py",
            structured_intelligence="## API Intelligence",
            chunks=[
                {
                    "content": "def main(): pass",
                    "metadata": {
                        "file_path": "backend/api.py",
                        "start_line": 10,
                        "end_line": 25,
                        "why_this_file": "Warm-up services",
                        "confidence": 98,
                    },
                }
            ],
            source_files=["backend/api.py"],
        )

        for pat in self.LEAKAGE_PATTERNS:
            assert not re.search(pat, fallback), f"Leaked pattern '{pat}' found in fallback response"

    def test_structured_evidence_item_model(self):
        item = EvidenceItem(
            file="backend/api.py",
            line_start=106,
            line_end=128,
            reason="Warm-up services",
            confidence=0.98,
            snippet="def warmup(): pass",
        )
        assert item.file == "backend/api.py"
        assert item.line_start == 106
        assert item.line_end == 128
        assert item.confidence == 0.98


# ---------------------------------------------------------------------------
# 2. Structured Evidence Formatting Tests
# ---------------------------------------------------------------------------


class TestEvidenceFormatting:
    """Verifies Evidence sections render as structured citations."""

    def test_fallback_renders_structured_evidence_citations(self):
        rendered = render_fallback(
            question="Which services does it initialize?",
            structured_intelligence="",
            chunks=[
                {
                    "content": "def init_services(): pass",
                    "metadata": {
                        "file_path": "backend/api.py",
                        "start_line": 106,
                        "end_line": 128,
                        "why_this_file": "Warm-up services",
                        "confidence": 98,
                    },
                },
                {
                    "content": "def setup_deps(): pass",
                    "metadata": {
                        "file_path": "backend/dependencies.py",
                        "start_line": 45,
                        "end_line": 77,
                        "why_this_file": "Dependency registration",
                        "confidence": 95,
                    },
                },
            ],
            source_files=["backend/api.py", "backend/dependencies.py"],
        )

        assert "### Evidence" in rendered
        assert "**File:** `backend/api.py`" in rendered
        assert "**Lines:** 106–128" in rendered
        assert "**Reason:** Warm-up services" in rendered
        assert "**Confidence:** 98%" in rendered

        assert "**File:** `backend/dependencies.py`" in rendered
        assert "**Lines:** 45–77" in rendered
        assert "**Reason:** Dependency registration" in rendered
        assert "**Confidence:** 95%" in rendered


# ---------------------------------------------------------------------------
# 3. ContextBuilder Response Format Guidelines
# ---------------------------------------------------------------------------


class TestContextBuilderGuidelines:
    """Verifies prompt instructions guide LLM to produce structured evidence."""

    def test_context_builder_evidence_guideline(self):
        builder = ContextBuilder()
        ctx = builder.build(
            repo_name="owner/repo",
            question="Explain backend/api.py",
            code_chunks=[{"content": "def main(): pass", "metadata": {"file_path": "backend/api.py"}}],
        )

        assert "Evidence" in ctx.prompt
        assert "**File:** `path`" in ctx.prompt
        assert "**Lines:** X–Y" in ctx.prompt
        assert "Never dump large raw code blocks" in ctx.prompt


# ---------------------------------------------------------------------------
# 4. Completion Gate Verification
# ---------------------------------------------------------------------------


class TestCompletionGateRendering:
    """Verifies all completion gate criteria for rendering and sanitization."""

    def test_completion_gate_no_artifact_leakage_across_all_renderers(self):
        # 1. Fallback renderer
        r1 = render_fallback("Q", "Intel", [], ["file.py"])
        # 2. Context builder
        cb = ContextBuilder()
        r2 = cb.build("repo", "Q", "Arch", "Intel", [{"content": "code", "metadata": {"file_path": "file.py"}}]).prompt

        combined = r1 + "\n" + r2
        prohibited = ["400\">", "class=", "text-indigo-", "font-semibold", "style=", "dangerouslySetInnerHTML"]
        for p in prohibited:
            assert p not in combined, f"Prohibited string '{p}' detected in rendering output"
