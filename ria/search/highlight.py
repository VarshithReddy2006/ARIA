"""Highlight Engine formatting match highlights."""

import re


class HighlightEngine:
    """Engine formatting search result text with match brackets."""

    def highlight(self, text: str, query: str) -> str:
        if not text or not query:
            return text
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return pattern.sub(lambda m: f"[{m.group(0)}]", text)
