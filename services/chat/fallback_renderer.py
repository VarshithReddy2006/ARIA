"""Fallback Renderer — Phase 10.

When the LLM is unavailable, renders a clean, professional response using
only the structured intelligence gathered from the repository.

Design principles:
  - NEVER dump hundreds of lines of raw code
  - NEVER expose provider names, API errors, or stack traces
  - ALWAYS show what was found, what's available, and what to try next
  - Structured format matching the Phase 11 answer template
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def render_fallback(
    question: str,
    structured_intelligence: str,
    chunks: List[Dict[str, Any]],
    source_files: List[str],
    fallback_reason: str = "unavailable",
    provider_error: str = "",
) -> str:
    """Render a professional fallback response when the LLM is unavailable.

    Args:
        question:                The user's question.
        structured_intelligence: Pre-built text from IntentRouter (may be empty).
        chunks:                  Retrieved code chunks from vector search.
        source_files:            All files referenced.
        fallback_reason:         Short reason code for observability.
        provider_error:          Raw error string (sanitised before display).

    Returns:
        A formatted markdown string suitable for streaming to the client.
    """
    sections: List[str] = []

    # Diagnose the issue for the user (sanitised — no raw tracebacks)
    diag = _diagnose_provider_error(provider_error)

    # Header + diagnosis
    sections.append(
        f"⚠️ **AI synthesis is temporarily unavailable.** {diag}\n"
        "Repository intelligence is still available.\n"
    )

    # Summary from structured intelligence
    if structured_intelligence.strip():
        sections.append("---\n")
        sections.append(structured_intelligence.strip())
        sections.append("\n")

    # Evidence citations (from chunks, structured)
    if chunks:
        sections.append("---\n")
        sections.append("### Evidence\n")
        seen_files: set = set()
        citations_shown = 0
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            file_path = meta.get("file_path", "")
            if not file_path or file_path in seen_files:
                continue
            seen_files.add(file_path)

            start_line = meta.get("start_line", 1)
            end_line = meta.get("end_line", start_line + 15)
            reason = meta.get("why_this_file", "Matched repository intelligence query")
            conf = meta.get("confidence")

            sections.append(f"**File:** `{file_path}`")
            sections.append(f"- **Lines:** {start_line}–{end_line}")
            sections.append(f"- **Reason:** {reason}")
            if conf is not None:
                sections.append(f"- **Confidence:** {conf}%\n")
            else:
                sections.append("")

            citations_shown += 1
            if citations_shown >= 5:
                break
    elif source_files:
        sections.append("---\n")
        sections.append("### Evidence\n")
        seen: set = set()
        for f in source_files:
            if f and f not in seen:
                seen.add(f)
                sections.append(f"**File:** `{f}`\n")

    # Suggested retry with actionable advice
    sections.append("---\n")
    sections.append("**Suggested Next Step**\n" + _retry_advice(provider_error))

    return "\n".join(sections)


def _diagnose_provider_error(error: str) -> str:
    """Return a user-facing diagnostic sentence from the raw provider error."""
    if not error:
        return ""
    e = error.lower()
    if "api_key_invalid" in e or "invalid api key" in e or "401" in e or "403" in e:
        return "The AI provider API key is invalid or expired."
    if "api key" in e and ("not set" in e or "missing" in e or "none" in e):
        return "The AI provider API key is not configured."
    if "429" in e or "rate limit" in e or "too many requests" in e:
        return "The AI provider rate limit has been reached."
    if "timeout" in e or "timed out" in e:
        return "The AI provider request timed out."
    if "503" in e or "502" in e or "service unavailable" in e or "bad gateway" in e:
        return "The AI provider is temporarily unavailable."
    if "connect" in e or "connection refused" in e or "network" in e:
        return "Could not connect to the AI provider."
    return ""


def _retry_advice(error: str) -> str:
    """Return actionable retry advice based on the error type."""
    if not error:
        return (
            "Please retry your question in a moment. "
            "If the issue persists, check your AI provider API key in `.env`.\n"
        )
    e = error.lower()
    if "api_key_invalid" in e or "invalid api key" in e or "401" in e or "403" in e:
        return (
            "Your API key appears to be invalid or expired. "
            "Update `GEMINI_API_KEY` in `.env`, then call `POST /api/chat/reload` "
            "or restart the backend.\n"
        )
    if "429" in e or "rate limit" in e:
        return "Rate limit reached. Please wait 60 seconds and retry.\n"
    if "not set" in e or "missing" in e or "none" in e:
        return (
            "Set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=<your-key>` in `.env`, "
            "then call `POST /api/chat/reload` or restart the backend.\n"
        )
    return (
        "Please retry your question in a moment. "
        "If the issue persists, check your AI provider API key in `.env`.\n"
    )


def render_mid_stream_termination(tokens_yielded: int) -> str:
    """Render a clean termination message when the LLM fails mid-stream.

    Args:
        tokens_yielded: How many tokens were already sent before failure.

    Returns:
        A short formatted message to append to the partial response.
    """
    return (
        "\n\n---\n"
        "⚠️ *The AI provider became unavailable mid-response. "
        "The answer above may be incomplete. "
        "Please retry your question to get a complete answer.*"
    )
