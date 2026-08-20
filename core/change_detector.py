"""Change detector for identifying added, modified, deleted, and renamed files (PH2-021)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from models.build_manifest import BuildManifest


@dataclass(frozen=True)
class ChangeSet:
    """An immutable representation of file changes in the repository."""

    added: Set[str]
    modified: Set[str]
    deleted: Set[str]
    renamed: Dict[str, str]  # old_path -> new_path
    unchanged: Set[str]
    repository_changed: bool


class ChangeDetector:
    """Detects file-level differences between repository states."""

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute the SHA-256 hash of a file's content."""
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

    @classmethod
    def compute_repository_hash(cls, file_hashes: Dict[str, str]) -> str:
        """Compute a deterministic repository hash from file path/content hashes."""
        sorted_paths = sorted(file_hashes.keys())
        hasher = hashlib.sha256()
        for path in sorted_paths:
            hasher.update(path.encode("utf-8", errors="replace"))
            hasher.update(file_hashes[path].encode("utf-8", errors="replace"))
        return hasher.hexdigest()

    @classmethod
    def scan_directory(cls, repo_path: str) -> List[Dict[str, str]]:
        """Walk directory and read supported files (mirroring extract_source_files)."""
        ignored_names = {
            "node_modules",
            ".git",
            "dist",
            "build",
            ".next",
            "venv",
            ".venv",
            "__pycache__",
            ".tox",
            "coverage",
            "data",
        }
        supported_exts = {".py", ".js", ".jsx", ".ts", ".tsx"}
        extracted_files = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ignored_names]
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)

                parts = rel_path.split(os.sep)
                if any(part in ignored_names for part in parts):
                    continue

                ext = os.path.splitext(file)[1].lower()
                if ext not in supported_exts:
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    extracted_files.append(
                        {"path": rel_path.replace(os.sep, "/"), "content": content}
                    )
                except Exception:
                    pass
        return extracted_files

    def detect_changes_from_hashes(
        self,
        current_hashes: Dict[str, str],
        old_manifest: Optional[BuildManifest],
    ) -> Tuple[ChangeSet, Dict[str, str], str]:
        """Compare precomputed file hashes with the previous manifest to identify differences.

        Args:
            current_hashes: Mapping of relative file path to its SHA-256 content hash.
            old_manifest: The BuildManifest from the last build, or None.

        Returns:
            A tuple of (ChangeSet, current_file_hashes, current_repository_hash).
        """
        current_repo_hash = self.compute_repository_hash(current_hashes)

        if not old_manifest:
            # First build: all files are added
            added = set(current_hashes.keys())
            change_set = ChangeSet(
                added=added,
                modified=set(),
                deleted=set(),
                renamed={},
                unchanged=set(),
                repository_changed=True,
            )
            return change_set, current_hashes, current_repo_hash

        old_hashes = old_manifest.file_hashes

        added_paths = set(current_hashes.keys()) - set(old_hashes.keys())
        deleted_paths = set(old_hashes.keys()) - set(current_hashes.keys())
        modified_paths = set()
        unchanged_paths = set()

        # Identify modified vs unchanged
        common_paths = set(current_hashes.keys()) & set(old_hashes.keys())
        for path in common_paths:
            if current_hashes[path] != old_hashes[path]:
                modified_paths.add(path)
            else:
                unchanged_paths.add(path)

        # Detect renames: a file is deleted and another is added with the same hash
        renamed = {}
        added_candidates = {current_hashes[p]: p for p in added_paths}

        for path in list(deleted_paths):
            h = old_hashes[path]
            if h in added_candidates:
                new_path = added_candidates[h]
                renamed[path] = new_path
                added_paths.remove(new_path)
                deleted_paths.remove(path)
                del added_candidates[h]

        repository_changed = current_repo_hash != old_manifest.repository_hash

        change_set = ChangeSet(
            added=added_paths,
            modified=modified_paths,
            deleted=deleted_paths,
            renamed=renamed,
            unchanged=unchanged_paths,
            repository_changed=repository_changed,
        )

        return change_set, current_hashes, current_repo_hash

    def detect_changes(
        self,
        current_files: List[Dict[str, str]],
        old_manifest: Optional[BuildManifest],
    ) -> Tuple[ChangeSet, Dict[str, str], str]:
        """Compare current files with the previous manifest to identify differences.

        Args:
            current_files: A list of dicts with {"path": str, "content": str}.
            old_manifest: The BuildManifest from the last build, or None.

        Returns:
            A tuple of (ChangeSet, current_file_hashes, current_repository_hash).
        """
        current_hashes = {
            f["path"]: self.compute_content_hash(f["content"])
            for f in current_files
            if f.get("path")
        }
        return self.detect_changes_from_hashes(current_hashes, old_manifest)
