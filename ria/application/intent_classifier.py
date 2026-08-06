"""Intent Classifier application service.

Classifies user query text into deterministic repository task intents (e.g., Explain Code,
Find Bug, Trace Dependency, Summarize Module, Architecture Review, Security Review,
Performance Review, Refactoring, Testing, Documentation) without AI/LLM calls.
Implements :class:`~ria.ports.context.IntentClassifierPort`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ria.domain.models.context_request import IntentClassification
from ria.ports.context import IntentClassifierPort

__all__ = ["IntentClassifierService"]

INTENT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "find_bug": (
        "bug",
        "error",
        "exception",
        "crash",
        "fix",
        "issue",
        "fault",
        "broken",
    ),
    "trace_dependency": (
        "depend",
        "import",
        "call",
        "usage",
        "chain",
        "reference",
        "where used",
    ),
    "summarize_module": (
        "summarize",
        "overview",
        "module",
        "package",
        "component",
        "structure",
    ),
    "architecture_review": (
        "architecture",
        "layer",
        "clean",
        "boundary",
        "violation",
        "pattern",
        "design",
    ),
    "security_review": (
        "security",
        "vulnerability",
        "auth",
        "secret",
        "sanitiz",
        "injection",
        "permission",
    ),
    "performance_review": (
        "performance",
        "latency",
        "slow",
        "bottleneck",
        "optimi",
        "memory",
        "speed",
    ),
    "refactoring": (
        "refactor",
        "rename",
        "clean code",
        "simplify",
        "extract",
        "decouple",
    ),
    "testing": ("test", "coverage", "mock", "assert", "unit test", "integration test"),
    "documentation": ("doc", "comment", "readme", "explain API", "specification"),
    "explain_code": ("explain", "understand", "how does", "what is", "describe"),
}


class IntentClassifierService(IntentClassifierPort):
    """Deterministic intent classifier implementation."""

    def classify_intent(self, query_text: str) -> IntentClassification:
        """Classify user query text into an IntentClassification using keyword matching."""
        text_lower = query_text.lower()

        scores: Dict[str, int] = {}
        matched_kw: Dict[str, List[str]] = {}

        for intent, keywords in INTENT_KEYWORDS.items():
            scores[intent] = 0
            matched_kw[intent] = []
            for kw in keywords:
                if kw in text_lower:
                    scores[intent] += 1
                    matched_kw[intent].append(kw)

        best_intent = max(scores, key=lambda k: scores[k])
        max_score = scores[best_intent]

        if max_score == 0:
            return IntentClassification(
                intent_type="explain_code", confidence=0.5, keywords=()
            )

        confidence = min(1.0, 0.5 + (max_score * 0.15))
        return IntentClassification(
            intent_type=best_intent,
            confidence=confidence,
            keywords=tuple(matched_kw[best_intent]),
        )
