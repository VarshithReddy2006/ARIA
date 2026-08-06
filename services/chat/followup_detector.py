"""Follow-up Detector — Standalone component classifying contextual queries.

Identifies follow-up questions vs fresh standalone searches.
Independent of TopicSwitchDetector so future topic switching capabilities (repository, branch, commit, PR)
can evolve independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from services.chat.conversation_context import ConversationContext


@dataclass(frozen=True, slots=True)
class FollowUpResult:
    """Immutable result of follow-up query classification."""

    is_followup: bool
    confidence: float
    followup_kind: (
        str  # e.g., "PRONOUN", "SHORT_QUERY", "METHOD_SERVICE", "WHY_HOW", "NONE"
    )


class FollowUpDetector:
    """Independent detector classifying contextual follow-up questions."""

    _PRONOUN_PATTERNS = [
        re.compile(r"\b(it|this|that|them|its|their|these|those)\b", re.I),
        re.compile(
            r"\b(who calls|where is it used|how does it|which services does it|why is that|what about)\b",
            re.I,
        ),
    ]

    _FOLLOWUP_OPENERS = [
        "how?",
        "why?",
        "where?",
        "what about it?",
        "who calls it?",
        "where is it used?",
        "how does it work?",
        "how is it initialized?",
        "does it support",
        "which services",
        "how does it manage",
        "why is that",
        "what responsibilities belong",
    ]

    def detect(
        self,
        question: str,
        context: Optional[ConversationContext] = None,
    ) -> FollowUpResult:
        """Classify if question is a follow-up query based on patterns and active context."""
        if not question or not question.strip():
            return FollowUpResult(
                is_followup=False, confidence=0.0, followup_kind="NONE"
            )

        q_clean = question.strip()
        q_lower = q_clean.lower()
        words = q_lower.split()

        has_active_topic = context is not None and (
            context.current_file is not None or context.current_symbol is not None
        )

        # 1. Single-word / short contextual query ("How?", "Why?", "Where?")
        if len(words) <= 3 and any(
            op in q_lower for op in ["how", "why", "where", "what", "who"]
        ):
            if has_active_topic:
                return FollowUpResult(
                    is_followup=True, confidence=0.95, followup_kind="SHORT_QUERY"
                )

        # 2. Known follow-up opener phrases
        for opener in self._FOLLOWUP_OPENERS:
            if q_lower.startswith(opener) or opener in q_lower:
                if has_active_topic or any(
                    pat.search(q_clean) for pat in self._PRONOUN_PATTERNS
                ):
                    return FollowUpResult(
                        is_followup=True,
                        confidence=0.92,
                        followup_kind="METHOD_SERVICE",
                    )

        # 3. Explicit pronoun match
        for pat in self._PRONOUN_PATTERNS:
            if pat.search(q_clean):
                return FollowUpResult(
                    is_followup=True, confidence=0.90, followup_kind="PRONOUN"
                )

        # 4. Question lacking file/symbol extensions when active file context exists
        contains_file_extension = bool(
            re.search(
                r"\b[\w-]+\.(py|ts|tsx|js|jsx|java|go|rs|md|toml|json|yml)\b", q_lower
            )
        )
        if has_active_topic and not contains_file_extension and len(words) <= 8:
            return FollowUpResult(
                is_followup=True, confidence=0.80, followup_kind="SHORT_CONTEXTUAL"
            )

        return FollowUpResult(is_followup=False, confidence=0.0, followup_kind="NONE")
