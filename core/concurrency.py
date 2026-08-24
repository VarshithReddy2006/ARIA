"""Concurrency utilities: repository-level locking and atomic file writes."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import uuid
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

# In-process per-repository lock registry
_REPO_LOCKS: Dict[str, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()


def get_repository_lock(repo_name: str) -> threading.Lock:
    """Get or create an in-process lock for a specific repository."""
    canonical_repo = repo_name.strip().lower()
    with _REGISTRY_LOCK:
        if canonical_repo not in _REPO_LOCKS:
            _REPO_LOCKS[canonical_repo] = threading.Lock()
        return _REPO_LOCKS[canonical_repo]


@contextlib.contextmanager
def repository_lock(
    repo_name: str, timeout: Optional[float] = None
) -> Generator[bool, None, None]:
    """Context manager acquiring exclusive write access for a given repository."""
    lock = get_repository_lock(repo_name)
    acquired = lock.acquire(timeout=timeout if timeout is not None else -1)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


def write_json_atomic(file_path: str, data: Any, indent: int = 2) -> None:
    """Write data to JSON file atomically using a temporary file and atomic replace.

    Guarantees that readers never observe partially written or truncated files.
    """
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    tmp_path = f"{file_path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, default=str)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        try:
            os.replace(tmp_path, file_path)
        except (OSError, PermissionError):
            try:
                import shutil

                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                shutil.move(tmp_path, file_path)
            except Exception:
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=indent, default=str)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        logger.error("Failed atomic write to %s: %s", file_path, exc)
        raise
