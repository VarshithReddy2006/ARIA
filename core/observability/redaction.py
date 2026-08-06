"""Redaction Filter Component.

Sanitizes sensitive data (API keys, Bearer tokens, JWTs, passwords, secrets)
before formatting or outputting log records.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict

# Patterns for sensitive data redaction
_SENSITIVE_PATTERNS = [
    # API Keys
    (re.compile(r"AIzaSy[a-zA-Z0-9_\-]{20,}"), "AIzaSy***REDACTED***"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "ghp_***REDACTED***"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{22,}"), "github_pat_***REDACTED***"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "sk-***REDACTED***"),
    # Bearer Tokens & JWTs
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.=]+", re.I), "Bearer ***REDACTED***"),
    (
        re.compile(r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"),
        "eyJ***REDACTED***",
    ),
    # Passwords and Secrets in key-value pairs
    (
        re.compile(
            r"""(?i)\b(password|passwd|secret|token|api[_\-]?key|authorization|cookie)\b\s*[:=]\s*['"]?([^\s'"&,;}]+)['"]?"""
        ),
        r"\1=***REDACTED***",
    ),
    # Connection Strings with password
    (
        re.compile(r"(?i)(postgres|mysql|mongodb|redis):\/\/([^:]+):([^@]+)@"),
        r"\1://\2:***REDACTED***@",
    ),
]


def sanitize_sensitive_data(val: Any) -> Any:
    """Recursively scrub sensitive keys and token values from string/dict/list objects."""
    if isinstance(val, str):
        result = val
        for pattern, replacement in _SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    elif isinstance(val, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in val.items():
            if any(
                s in k.lower()
                for s in (
                    "password",
                    "secret",
                    "token",
                    "api_key",
                    "apikey",
                    "authorization",
                )
            ):
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = sanitize_sensitive_data(v)
        return cleaned
    elif isinstance(val, list):
        return [sanitize_sensitive_data(item) for item in val]
    elif isinstance(val, tuple):
        return tuple(sanitize_sensitive_data(item) for item in val)
    return val


class RedactionFilter(logging.Filter):
    """Logging filter that redacts sensitive information from log record messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_sensitive_data(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_sensitive_data(record.args)
            elif isinstance(record.args, tuple):
                record.args = sanitize_sensitive_data(record.args)
        return True
