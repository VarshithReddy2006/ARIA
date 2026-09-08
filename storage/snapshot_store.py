"""Snapshot storage abstractions and implementations (PH2-002)."""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import threading

logger = logging.getLogger(__name__)


class SnapshotStore(ABC):
    """Abstract base class for analysis snapshot storage backends."""

    @abstractmethod
    def load(
        self, repo_name: str, key: str, subkey: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load a snapshot payload."""
        pass

    @abstractmethod
    def save(
        self,
        repo_name: str,
        key: str,
        data: Dict[str, Any],
        subkey: Optional[str] = None,
    ) -> None:
        """Save a snapshot payload."""
        pass

    @abstractmethod
    def exists(self, repo_name: str, key: str, subkey: Optional[str] = None) -> bool:
        """Check if a snapshot exists."""
        pass

    @abstractmethod
    def delete(self, repo_name: str, key: str, subkey: Optional[str] = None) -> None:
        """Delete a snapshot."""
        pass

    @abstractmethod
    def list(self, repo_name: str, key: str) -> List[str]:
        """List all snapshot filenames matching the repository and key."""
        pass


class JsonSnapshotStore(SnapshotStore):
    """File-system based JSON snapshot storage implementation."""

    def __init__(
        self, base_dir: Optional[str] = None, key_map: Optional[Dict[str, str]] = None
    ) -> None:
        """Initialise the JSON snapshot store.

        Args:
            base_dir: Root directory of data folder (defaults to absolute path
                      to project-root/data).
            key_map: Optional mapping of standard keys to custom directory names.
        """
        if base_dir is None:
            # Default to projects/Repo-Intelligence-Agent/data
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
            )
        self.base_dir = base_dir
        self.key_map = key_map or {}
        self._lock = threading.Lock()

    def _get_path(self, repo_name: str, key: str, subkey: Optional[str] = None) -> str:
        safe_repo = repo_name.replace("/", "_").replace("\\", "_")
        dir_name = self.key_map.get(key, key)
        dir_path = os.path.join(self.base_dir, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        if subkey:
            filename = f"{safe_repo}_{subkey}.json"
        else:
            filename = f"{safe_repo}.json"
        return os.path.join(dir_path, filename)

    def _resolve_path(
        self, repo_name: str, key: str, subkey: Optional[str] = None
    ) -> Optional[str]:
        """Resolve snapshot filepath supporting case-insensitivity and canonical aliases across OSes."""
        direct_path = self._get_path(repo_name, key, subkey)
        if os.path.exists(direct_path):
            return direct_path

        dir_name = self.key_map.get(key, key)
        dir_path = os.path.join(self.base_dir, dir_name)
        if not os.path.isdir(dir_path):
            return None

        # 1. Case-insensitive filename match (Linux compatibility)
        target_fn = os.path.basename(direct_path).lower()
        try:
            entries = os.listdir(dir_path)
        except Exception:
            entries = []

        for entry in entries:
            if entry.lower() == target_fn:
                return os.path.join(dir_path, entry)

        # 2. Canonical repository name resolution
        candidate_names: List[str] = []
        try:
            from core.repository_target import get_canonical_repo_id

            canon = get_canonical_repo_id(repo_name)
            if canon != repo_name and canon not in candidate_names:
                candidate_names.append(canon)
        except Exception:
            pass

        # 3. Known ARIA / Repo-Intelligence-Agent repository aliases
        repo_clean = repo_name.strip().lower()
        if "repo-intelligence-agent" in repo_clean or "aria" in repo_clean:
            for alias in (
                "varshithreddy2006/aria",
                "VarshithReddy2006/ARIA",
                "VarshithReddy2006/Repo-Intelligence-Agent",
                "varshithreddy2006/repo-intelligence-agent",
                "Repo-Intelligence-Agent",
                "ARIA",
            ):
                if alias != repo_name and alias not in candidate_names:
                    candidate_names.append(alias)

        for cand in candidate_names:
            cand_p = self._get_path(cand, key, subkey)
            if os.path.exists(cand_p):
                return cand_p
            cand_fn = os.path.basename(cand_p).lower()
            for entry in entries:
                if entry.lower() == cand_fn:
                    return os.path.join(dir_path, entry)

        return None

    def load(
        self, repo_name: str, key: str, subkey: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            path = self._resolve_path(repo_name, key, subkey)
            if not path or not os.path.exists(path):
                return None
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception as exc:
                logger.error("Failed to load snapshot from %s: %s", path, exc)
                return None

    def save(
        self,
        repo_name: str,
        key: str,
        data: Dict[str, Any],
        subkey: Optional[str] = None,
    ) -> None:
        from core.concurrency import write_json_atomic

        with self._lock:
            path = self._get_path(repo_name, key, subkey)
            try:
                write_json_atomic(path, data, indent=2)
                logger.debug("Saved JSON snapshot to %s", path)
            except Exception as exc:
                logger.error("Failed to save snapshot to %s: %s", path, exc)
                raise

    def exists(self, repo_name: str, key: str, subkey: Optional[str] = None) -> bool:
        with self._lock:
            path = self._resolve_path(repo_name, key, subkey)
            return path is not None and os.path.exists(path)

    def delete(self, repo_name: str, key: str, subkey: Optional[str] = None) -> None:
        with self._lock:
            path = self._resolve_path(repo_name, key, subkey)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info("Deleted snapshot from %s", path)
                except Exception as exc:
                    logger.error("Failed to delete snapshot %s: %s", path, exc)

    def list(self, repo_name: str, key: str) -> List[str]:
        with self._lock:
            dir_path = os.path.join(self.base_dir, key)
            if not os.path.exists(dir_path):
                return []
            safe_repo = repo_name.replace("/", "_")
            matches = []
            try:
                for entry in os.listdir(dir_path):
                    if entry.startswith(safe_repo) and entry.endswith(".json"):
                        matches.append(entry)
            except Exception as exc:
                logger.error("Failed to list snapshots in %s: %s", dir_path, exc)
            return matches
