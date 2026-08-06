"""Conversation Settings — Configurable parameters for conversation-aware retrieval.

Replaces hardcoded magic numbers with a clean, immutable configuration container.
Can be overridden per session or loaded from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ConversationSettings:
    """Immutable settings container for conversation intelligence."""

    topic_initial_confidence: float = 0.98
    topic_switch_confidence: float = 0.98
    topic_decay_rate: float = 0.15
    topic_threshold: float = 0.35
    max_recent_files: int = 10
    max_recent_symbols: int = 20
    max_history: int = 10
    current_file_boost: float = 50.0
    current_symbol_boost: float = 35.0
    current_module_boost: float = 20.0
    repository_boost: float = 10.0
    recent_file_boost: float = 10.0
    debug_chat: bool = field(
        default_factory=lambda: (
            os.getenv("DEBUG_CHAT", "false").lower() in ("true", "1", "yes")
        )
    )

    @classmethod
    def default(cls) -> ConversationSettings:
        return cls()
