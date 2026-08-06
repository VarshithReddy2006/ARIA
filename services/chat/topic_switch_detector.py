"""Topic Switch Detector — Standalone component detecting topic transitions.

Identifies explicit topic changes ("Switch to...", "Now explain...", "Forget...", "Move to...",
"How does that compare to...", or introduction of an unanchored new file/symbol/entity).
Integrates with ExplicitEntityResolver to ensure explicit entity mentions trigger immediate topic switches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from services.chat.conversation_context import ConversationContext
from services.chat.explicit_entity_resolver import ExplicitEntityResult


@dataclass(frozen=True, slots=True)
class TopicSwitchResult:
    """Immutable result of topic switch detection."""

    is_topic_switch: bool
    switch_kind: str  # e.g., "EXPLICIT_ENTITY", "EXPLICIT_COMMAND", "FILE_TRANSITION", "COMPARISON_TRANSITION", "SYMBOL_TRANSITION", "NONE"
    target_file: Optional[str]
    target_symbol: Optional[str]
    confidence: float


class TopicSwitchDetector:
    """Independent detector classifying explicit topic switches."""

    _SWITCH_PREFIXES = [
        "switch to",
        "now explain",
        "forget",
        "move to",
        "let's look at",
        "show me",
        "focus on",
        "explain",
    ]

    _FILE_PATTERN = re.compile(
        r"\b([a-zA-Z0-9_\-\./\\]+\.(?:py|ts|tsx|js|jsx|java|go|rs|md|toml|json|yml))\b",
        re.I,
    )

    def detect(
        self,
        question: str,
        context: Optional[ConversationContext] = None,
        explicit_res: Optional[ExplicitEntityResult] = None,
    ) -> TopicSwitchResult:
        """Classify if question triggers a topic switch."""
        if not question or not question.strip():
            return TopicSwitchResult(
                is_topic_switch=False,
                switch_kind="NONE",
                target_file=None,
                target_symbol=None,
                confidence=0.0,
            )

        q_clean = question.strip()
        q_lower = q_clean.lower()

        current_file = context.current_file if context else None
        current_file_norm = (
            current_file.replace("\\", "/").lower() if current_file else None
        )
        current_symbol = context.current_symbol if context else None
        current_symbol_norm = current_symbol.lower() if current_symbol else None

        # 1. Trigger from ExplicitEntityResolver if an explicit entity was discovered
        if explicit_res and explicit_res.has_explicit_entity:
            target_f = explicit_res.target_file
            target_s = explicit_res.target_symbol

            is_diff_file = target_f and (
                not current_file_norm
                or (
                    target_f.lower() != current_file_norm
                    and not current_file_norm.endswith("/" + target_f.lower())
                )
            )
            is_diff_sym = target_s and (
                not current_symbol_norm or target_s.lower() != current_symbol_norm
            )

            if is_diff_file or is_diff_sym or not current_file_norm:
                return TopicSwitchResult(
                    is_topic_switch=True,
                    switch_kind="EXPLICIT_ENTITY",
                    target_file=target_f,
                    target_symbol=target_s or explicit_res.entity_name,
                    confidence=0.99,
                )

        # 2. Extract explicit files in question
        matches = self._FILE_PATTERN.findall(q_clean)
        extracted_file = matches[0].replace("\\", "/") if matches else None

        # Comparison transition ("How does that compare to backend/dependencies.py?")
        if (
            "compare to" in q_lower
            or "differs from" in q_lower
            or "versus" in q_lower
            or "vs" in q_lower
        ) and extracted_file:
            if (
                current_file_norm
                and extracted_file.lower() != current_file_norm
                and not current_file_norm.endswith("/" + extracted_file.lower())
            ):
                return TopicSwitchResult(
                    is_topic_switch=True,
                    switch_kind="COMPARISON_TRANSITION",
                    target_file=extracted_file,
                    target_symbol=None,
                    confidence=0.98,
                )

        # Explicit switch command ("Switch to services/workspace.py", "Now explain graph_rag.py")
        for prefix in self._SWITCH_PREFIXES:
            if q_lower.startswith(prefix) or f" {prefix} " in q_lower:
                if extracted_file:
                    if not current_file_norm or (
                        extracted_file.lower() != current_file_norm
                        and not current_file_norm.endswith("/" + extracted_file.lower())
                    ):
                        return TopicSwitchResult(
                            is_topic_switch=True,
                            switch_kind="EXPLICIT_COMMAND",
                            target_file=extracted_file,
                            target_symbol=None,
                            confidence=0.99,
                        )

        # New file introduced that differs from current topic
        if extracted_file:
            if not current_file_norm:
                return TopicSwitchResult(
                    is_topic_switch=True,
                    switch_kind="FILE_TRANSITION",
                    target_file=extracted_file,
                    target_symbol=None,
                    confidence=0.95,
                )
            elif (
                extracted_file.lower() != current_file_norm
                and not current_file_norm.endswith("/" + extracted_file.lower())
            ):
                return TopicSwitchResult(
                    is_topic_switch=True,
                    switch_kind="FILE_TRANSITION",
                    target_file=extracted_file,
                    target_symbol=None,
                    confidence=0.95,
                )

        return TopicSwitchResult(
            is_topic_switch=False,
            switch_kind="NONE",
            target_file=None,
            target_symbol=None,
            confidence=0.0,
        )
