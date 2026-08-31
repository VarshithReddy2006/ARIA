"""Canonical Analysis Target Identity & Normalization Model (Phase 1).

Provides a single, deterministic identity model for repositories, branches, and refs
to prevent branch collisions, working tree overwrites, and race conditions across
processes and threads.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple


# Characters not allowed in directory/file names across Linux, macOS, Windows
_UNSAFE_PATH_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_MAX_REF_PATH_LENGTH = 48


def normalize_repository_name(repo_url_or_name: str) -> Tuple[str, str]:
    """Deterministically parse and normalize repository owner and name.

    Returns:
        Tuple of (owner, repo) in lower-case trimmed format.
    """
    clean = repo_url_or_name.strip()
    if clean.endswith(".git"):
        clean = clean[:-4]

    # Handle git@ or http(s):// URLs
    if "github.com/" in clean:
        clean = clean.split("github.com/")[-1]
    elif "github.com:" in clean:
        clean = clean.split("github.com:")[-1]

    parts = [p.strip() for p in clean.strip("/").split("/") if p.strip()]
    if len(parts) >= 2:
        owner = parts[-2].lower()
        repo = parts[-1].lower()
        return owner, repo
    elif len(parts) == 1:
        return "owner", parts[0].lower()
    return "owner", "repo"


def get_canonical_repo_id(repo_url_or_name: str) -> str:
    """Return canonical 'owner/repo' string."""
    owner, repo = normalize_repository_name(repo_url_or_name)
    return f"{owner}/{repo}"


def normalize_ref(ref: Optional[str]) -> str:
    """Normalize git branch/tag/ref name. Defaults to 'main' if empty."""
    if not ref or not isinstance(ref, str):
        return "main"
    cleaned = ref.strip()
    return cleaned if cleaned else "main"


def normalize_ref_for_path(ref: Optional[str]) -> str:
    """Convert a git ref into a safe, deterministic, collision-resistant directory name.

    Guarantees:
      1. Path traversal attacks (..) cannot escape the base directory.
      2. Invalid filesystem characters are converted to safe underscores.
      3. Slash-containing refs ('feature/auth', 'refs/pull/101/head') are normalized cleanly.
      4. Excessive length or illegal character injection is bounded with a short SHA-256 hash.
    """
    raw_ref = normalize_ref(ref)

    # Standardize slash separators and remove leading/trailing slashes
    sanitized = raw_ref.strip("/").replace("\\", "/")

    # Check path traversal attempts
    has_traversal = ".." in sanitized
    sanitized = re.sub(r"\.\.+", "_", sanitized)

    # Convert slashes to underscores for single-level branch directory nesting
    sanitized = sanitized.replace("/", "_")

    # Check and replace any remaining unsafe characters
    has_illegal = bool(_UNSAFE_PATH_CHARS_PATTERN.search(sanitized))
    sanitized = _UNSAFE_PATH_CHARS_PATTERN.sub("_", sanitized)

    # Compress multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        sanitized = "main"

    is_reserved = sanitized.lower() in (
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "lpt1",
    )
    is_too_long = len(sanitized) > _MAX_REF_PATH_LENGTH

    if is_too_long or has_traversal or has_illegal or is_reserved:
        ref_hash = hashlib.sha256(raw_ref.encode("utf-8")).hexdigest()[:8]
        truncated = sanitized[:_MAX_REF_PATH_LENGTH].rstrip("_")
        return f"{truncated}_{ref_hash}"

    return sanitized


@dataclass(frozen=True)
class AnalysisTarget:
    """Canonical, immutable analysis target representation."""

    owner: str
    repo: str
    ref: str
    commit_sha: Optional[str] = None

    @classmethod
    def from_url_and_branch(
        cls,
        repo_url_or_name: str,
        branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> AnalysisTarget:
        owner, repo = normalize_repository_name(repo_url_or_name)
        ref = normalize_ref(branch)
        clean_sha = (
            commit_sha.strip().lower()
            if commit_sha and isinstance(commit_sha, str)
            else None
        )
        return cls(owner=owner, repo=repo, ref=ref, commit_sha=clean_sha)

    @property
    def repo_id(self) -> str:
        """Canonical 'owner/repo' identifier."""
        return f"{self.owner}/{self.repo}"

    @property
    def safe_repo_dir(self) -> str:
        """Safe directory component for repository: 'owner_repo'."""
        return f"{self.owner}_{self.repo}"

    @property
    def safe_ref_dir(self) -> str:
        """Safe directory component for ref/branch."""
        return normalize_ref_for_path(self.ref)

    @property
    def target_key(self) -> str:
        """Deterministic target key: 'owner/repo::ref' or 'owner/repo::ref@sha'."""
        base = f"{self.owner}/{self.repo}::{self.ref.lower()}"
        if self.commit_sha:
            return f"{base}@{self.commit_sha[:12]}"
        return base

    @property
    def lock_name(self) -> str:
        """Safe filename base for file locking."""
        ref_part = self.safe_ref_dir
        return f"{self.owner}_{self.repo}_{ref_part}"


def get_analysis_target_key(
    repo_name_or_url: str,
    branch: Optional[str] = None,
    commit_sha: Optional[str] = None,
) -> str:
    """Convenience helper to compute target key from strings."""
    return AnalysisTarget.from_url_and_branch(
        repo_name_or_url, branch, commit_sha
    ).target_key


def get_repository_lock_path(
    repo_name_or_url: str,
    branch: Optional[str] = None,
    base_lock_dir: Optional[str] = None,
) -> str:
    """Resolve full path to lockfile for a specific analysis target."""
    target = AnalysisTarget.from_url_and_branch(repo_name_or_url, branch)
    if base_lock_dir is None:
        base_lock_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "locks",
            "repositories",
        )
    os.makedirs(base_lock_dir, exist_ok=True)
    return os.path.join(base_lock_dir, f"{target.lock_name}.lock")
