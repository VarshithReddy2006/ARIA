"""Git History & Churn Analysis Service.

Mines the local git repository (cloned by GitHubService) to produce
file-level churn scores, hotspot detection, author ownership maps, and
weekly commit timelines.

Design principles:
  - Uses subprocess + git log directly, matching the existing GitHubService
    pattern (no new git-python / dulwich dependency).
  - All computation is pure Python arithmetic — zero LLM calls.
  - Persists results to data/churn/{owner}_{repo}_{since_days}.json using
    the same atomic-write + schema-version pattern as ArchitectureService
    and SymbolService.
  - Graph centrality overlay reuses the existing GraphService.load_graph()
    call — no graph rebuild required.

Supported: any repository cloned by GitHubService (Python, JS, TS, and
beyond — git history is language-agnostic).
"""

from __future__ import annotations

import logging
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from utils.subprocess_runner import (
    run_safe_command,
    SafeSubprocessError,
    SHORT_GIT_TIMEOUT,
    HISTORY_ANALYSIS_TIMEOUT,
)

import networkx as nx

from models.churn import (
    AuthorOwnership,
    ChurnSummary,
    FileChurnRecord,
    HotspotFile,
    TimelineEntry,
)
from services.github_service import GitHubService
from services.graph_service import GraphService
from storage.snapshot_store import SnapshotStore
from core.cache import AnalysisCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_CHURN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "churn",
)

# Increment when schema or algorithm changes.
_SCHEMA_VERSION = 1

# Minimum commits for shallow-clone detection heuristic.
_SHALLOW_CLONE_THRESHOLD = 20

# Top-N hotspots to return in the summary.
_DEFAULT_TOP_HOTSPOTS = 25


class GitHistoryService:
    """Mines git history and computes file-level churn metrics.

    Intended as a singleton injected into the FastAPI app (same pattern as
    GraphService, SymbolService, etc.).
    """

    @property
    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    @classmethod
    def get_schema_version(cls) -> int:
        return _SCHEMA_VERSION

    def __init__(
        self,
        github_service: Optional[GitHubService] = None,
        graph_service: Optional[GraphService] = None,
        churn_dir: str = _CHURN_DIR,
        snapshot_store: Optional[SnapshotStore] = None,
        analysis_cache: Optional[AnalysisCache] = None,
    ) -> None:
        self.github_service = github_service or GitHubService()
        self.graph_service = graph_service or GraphService()
        self.churn_dir = churn_dir
        os.makedirs(self.churn_dir, exist_ok=True)

        if snapshot_store is None:
            if churn_dir != _CHURN_DIR:
                parent_dir = os.path.dirname(churn_dir)
                dir_name = os.path.basename(churn_dir)
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore(
                    base_dir=parent_dir, key_map={"churn": dir_name}
                )
            else:
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore()
        else:
            self.snapshot_store = snapshot_store

        self.analysis_cache = analysis_cache or AnalysisCache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        repo_name: str,
        since_days: int = 365,
    ) -> Generator[Dict[str, Any], None, ChurnSummary]:
        """Mine git history and compute churn. Yields SSE-style progress dicts.

        This is a generator so the FastAPI endpoint can stream progress events
        exactly as /api/analyze does.

        Usage::
            gen = service.build(repo_name, since_days)
            for event in gen:
                yield sse(event)
            summary = gen.value   # ChurnSummary returned via StopIteration.value

        Args:
            repo_name:  Repository identifier (owner/repo).
            since_days: Number of days of history to mine.

        Yields:
            Dict with { status, message } suitable for SSE streaming.

        Returns (via StopIteration.value):
            Populated ChurnSummary.
        """
        repo_path = self.github_service.get_local_repo_path(repo_name)
        if not os.path.isdir(repo_path):
            raise ValueError(
                f"Repository '{repo_name}' is not cloned locally. "
                "Run POST /api/analyze first."
            )

        yield {"status": "mining", "message": "Mining git commit history…"}

        # ── Step 1: mine raw commits ──────────────────────────────────
        commits, shallow_warning = self._mine_commits(repo_path, since_days)
        total_commits = len(commits)
        logger.info(
            "[ChurnService:%s] Mined %d commits (since_days=%d)",
            repo_name,
            total_commits,
            since_days,
        )
        yield {
            "status": "mining_done",
            "message": f"✓ {total_commits} commits collected",
        }

        # ── Step 2: aggregate per-file stats ─────────────────────────
        yield {"status": "computing", "message": "Computing churn scores…"}
        raw_churn = self._aggregate_churn(commits)
        raw_ownership = self._aggregate_ownership(commits)

        # ── Step 3: normalise churn scores ────────────────────────────
        file_records = self._normalise(raw_churn, raw_ownership)
        yield {
            "status": "normalised",
            "message": f"✓ {len(file_records)} files scored",
        }

        # ── Step 4: load graph for centrality overlay ─────────────────
        yield {
            "status": "graph",
            "message": "Loading dependency graph for hotspot overlay…",
        }
        graph = self.graph_service.load_graph(repo_name)
        centrality: Dict[str, float] = {}
        if graph and graph.number_of_nodes() > 0:
            centrality = nx.degree_centrality(graph)

        # ── Step 5: compute hotspots ──────────────────────────────────
        hotspots = self._compute_hotspots(file_records, centrality)
        yield {
            "status": "hotspots",
            "message": f"✓ {len(hotspots)} hotspot files identified",
        }

        # ── Step 6: build author ownership list ───────────────────────
        ownership_list = self._build_ownership_list(raw_ownership)

        # ── Step 7: build timeline ────────────────────────────────────
        timeline = self._build_timeline(commits)

        # ── Step 8: persist ───────────────────────────────────────────
        yield {"status": "saving", "message": "Saving churn report…"}
        summary = ChurnSummary(
            repo=repo_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            since_days=since_days,
            total_commits=total_commits,
            total_files=len(file_records),
            hotspots=hotspots,
            file_records=file_records,
            author_ownership=ownership_list,
            timeline=timeline,
            warning=shallow_warning,
        )
        self._save(repo_name, since_days, summary)
        logger.info("[ChurnService:%s] Churn report saved.", repo_name)
        yield {"status": "complete", "message": "✓ Churn analysis complete"}

        return summary

    def load(self, repo_name: str, since_days: int = 365) -> Optional[ChurnSummary]:
        """Load a persisted churn summary from disk.

        Returns:
            ChurnSummary or None if not found / stale schema.
        """
        subkey = f"{since_days}d"
        cached = self.analysis_cache.get(
            repo_name, "churn", _SCHEMA_VERSION, subkey=subkey
        )
        if cached is not None:
            return cached

        data = self.snapshot_store.load(repo_name, "churn", subkey=subkey)
        if data is None:
            return None

        stored_ver = data.get("_schema_version", 0)
        if stored_ver < _SCHEMA_VERSION:
            logger.warning(
                "Discarding stale churn summary for %s (v%d < v%d)",
                repo_name,
                stored_ver,
                _SCHEMA_VERSION,
            )
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            summary = ChurnSummary(**filtered)
            self.analysis_cache.set(
                repo_name, "churn", summary, _SCHEMA_VERSION, subkey=subkey
            )
            return summary
        except Exception as exc:
            logger.error(
                "Failed to deserialise churn summary for %s: %s", repo_name, exc
            )
            return None

    def summary_exists(self, repo_name: str, since_days: int = 365) -> bool:
        """Return True if a valid persisted churn report exists."""
        return self.snapshot_store.exists(repo_name, "churn", subkey=f"{since_days}d")

    def get_hotspots(
        self,
        repo_name: str,
        since_days: int = 365,
        top_n: int = _DEFAULT_TOP_HOTSPOTS,
    ) -> List[HotspotFile]:
        """Return the top-N hotspot files from a cached report."""
        summary = self.load(repo_name, since_days)
        if summary is None:
            return []
        return summary.hotspots[:top_n]

    def get_file_record(
        self, repo_name: str, file_path: str, since_days: int = 365
    ) -> Optional[FileChurnRecord]:
        """Return the churn record for a specific file."""
        summary = self.load(repo_name, since_days)
        if summary is None:
            return None
        norm = file_path.replace("\\", "/")
        for rec in summary.file_records:
            if rec.file_path.replace("\\", "/") == norm:
                return rec
        return None

    # ------------------------------------------------------------------
    # Step 1 — Git log mining
    # ------------------------------------------------------------------

    def _mine_commits(
        self, repo_path: str, since_days: int
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Run git log and parse into a list of commit records.

        Uses --name-status to get per-file change info and --no-merges to
        avoid inflating counts with merge commits.

        Returns:
            (commits, shallow_warning_or_None)
        """
        since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime(
            "%Y-%m-%d"
        )

        cmd = [
            "git",
            "-C",
            repo_path,
            "log",
            "--no-merges",
            "--name-status",
            f"--since={since_date}",
            "--format=COMMIT|%H|%ae|%aI",
            "--diff-filter=ACDMRT",  # exclude untracked & copied; include renames
        ]

        try:
            result = run_safe_command(
                cmd,
                timeout=HISTORY_ANALYSIS_TIMEOUT,
            )
        except SafeSubprocessError as err:
            if err.timed_out:
                logger.warning("git log timed out for %s", repo_path)
                return [], "git log timed out — history may be incomplete."
            logger.warning("git log error: %s", err.stderr[:200])
            return [], f"git log error: {err.stderr[:200]}"
        except Exception as exc:
            logger.warning("git log exception: %s", str(exc)[:200])
            return [], f"git log error: {str(exc)[:200]}"

        if result.returncode != 0:
            logger.warning("git log error: %s", result.stderr[:200])
            return [], f"git log error: {result.stderr[:200]}"

        commits = self._parse_git_log(result.stdout)

        # Shallow clone detection
        warning: Optional[str] = None
        total_all_time = self._count_all_commits(repo_path)
        if total_all_time < _SHALLOW_CLONE_THRESHOLD:
            warning = (
                f"Shallow clone detected ({total_all_time} total commits). "
                "Churn analysis is based on limited history. "
                "Re-clone without --depth=1 for accurate results."
            )

        return commits, warning

    @staticmethod
    def _parse_git_log(stdout: str) -> List[Dict[str, Any]]:
        """Parse git log --name-status output into structured commit records.

        The log format mixes COMMIT| header lines with file-status lines:
            COMMIT|<hash>|<email>|<ISO date>
            M\tpath/to/file.py
            R100\told/path.py\tnew/path.py
            A\tnew/file.ts

        Returns:
            List of { hash, author, date, files: [{path, status, insertions, deletions}] }
            Note: insertions/deletions are not available from --name-status alone;
            they default to 0 and are enriched via --numstat when needed. For
            the churn score formula (commit_count × 0.5) the line count is
            additive — we track it as a separate pass below.
        """
        commits: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for line in stdout.splitlines():
            line = line.rstrip()
            if not line:
                continue

            if line.startswith("COMMIT|"):
                if current:
                    commits.append(current)
                parts = line.split("|", 3)
                current = {
                    "hash": parts[1] if len(parts) > 1 else "",
                    "author": parts[2] if len(parts) > 2 else "",
                    "date": parts[3] if len(parts) > 3 else "",
                    "files": [],
                }
                continue

            if current is None:
                continue

            # Rename: R100\told_path\tnew_path  or  R\told\tnew
            if line.startswith("R"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    new_path = parts[2].replace("\\", "/")
                    current["files"].append({"path": new_path, "status": "renamed"})
                continue

            # Copy: C\told\tnew
            if line.startswith("C"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    new_path = parts[2].replace("\\", "/")
                    current["files"].append({"path": new_path, "status": "copied"})
                continue

            # Standard: M/A/D/T\tpath
            parts = line.split("\t")
            if len(parts) >= 2:
                status_char = parts[0].strip()
                path = parts[1].strip().replace("\\", "/")
                status_map = {
                    "M": "modified",
                    "A": "added",
                    "D": "deleted",
                    "T": "modified",
                }
                status = status_map.get(status_char, "modified")
                current["files"].append({"path": path, "status": status})

        if current:
            commits.append(current)

        return commits

    @staticmethod
    def _count_all_commits(repo_path: str) -> int:
        """Count total commits regardless of date window."""
        try:
            res = run_safe_command(
                ["git", "-C", repo_path, "rev-list", "--count", "HEAD"],
                timeout=SHORT_GIT_TIMEOUT,
            )
            return int(res.stdout.strip()) if res.returncode == 0 else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Step 2 — Churn aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_churn(
        commits: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Aggregate raw commit counts and track dates per file.

        Returns:
            { file_path → { commit_count, last_commit_date, is_deleted } }
        """
        records: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "commit_count": 0,
                "last_commit_date": "",
                "is_deleted": False,
            }
        )

        for commit in commits:
            date = commit.get("date", "")
            for f in commit.get("files", []):
                path = f["path"]
                rec = records[path]
                rec["commit_count"] += 1
                if not rec["last_commit_date"] or date > rec["last_commit_date"]:
                    rec["last_commit_date"] = date
                if f["status"] == "deleted":
                    rec["is_deleted"] = True
                elif f["status"] in ("modified", "added", "renamed", "copied"):
                    # A rename/re-add after deletion means it's back
                    rec["is_deleted"] = False

        return dict(records)

    @staticmethod
    def _aggregate_ownership(
        commits: List[Dict[str, Any]],
    ) -> Dict[str, Counter]:
        """Count commits per author per file.

        Returns:
            { file_path → Counter({ author_email → commit_count }) }
        """
        ownership: Dict[str, Counter] = defaultdict(Counter)
        for commit in commits:
            author = commit.get("author", "unknown")
            for f in commit.get("files", []):
                ownership[f["path"]][author] += 1
        return dict(ownership)

    # ------------------------------------------------------------------
    # Step 3 — Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(
        raw_churn: Dict[str, Dict[str, Any]],
        raw_ownership: Dict[str, Counter],
    ) -> List[FileChurnRecord]:
        """Convert raw aggregation dicts into normalised FileChurnRecord list.

        Churn score formula:
            raw_score(f) = commit_count(f)
            churn_score(f) = (raw_score / max_raw) × 100   (0–100)

        The formula is intentionally simple — commit count is the most
        reliable churn signal for a shallow clone; line-delta tracking
        would require a separate --numstat pass which is costly on large
        histories.
        """
        if not raw_churn:
            return []

        max_commits = max(r["commit_count"] for r in raw_churn.values()) or 1

        records: List[FileChurnRecord] = []
        for path, churn in raw_churn.items():
            commit_count = churn["commit_count"]
            churn_score = round((commit_count / max_commits) * 100.0, 2)

            author_counter = raw_ownership.get(path, Counter())
            total = sum(author_counter.values()) or 1
            primary_author = (
                author_counter.most_common(1)[0][0] if author_counter else ""
            )
            primary_count = author_counter.most_common(1)[0][1] if author_counter else 0
            bus_factor_risk = (primary_count / total) > 0.8

            records.append(
                FileChurnRecord(
                    file_path=path,
                    commit_count=commit_count,
                    insertions=0,  # enriched in future pass if needed
                    deletions=0,
                    churn_score=churn_score,
                    primary_author=primary_author,
                    author_count=len(author_counter),
                    bus_factor_risk=bus_factor_risk,
                    last_commit_date=churn.get("last_commit_date", ""),
                    is_deleted=churn.get("is_deleted", False),
                )
            )

        return sorted(records, key=lambda r: r.churn_score, reverse=True)

    # ------------------------------------------------------------------
    # Step 5 — Hotspot computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hotspots(
        file_records: List[FileChurnRecord],
        centrality: Dict[str, float],
        top_n: int = _DEFAULT_TOP_HOTSPOTS,
    ) -> List[HotspotFile]:
        """Cross-reference churn scores with graph centrality.

        hotspot_score(f) = churn_score(f) × (1 + centrality(f))

        Files that are both heavily churned AND structurally central receive
        the highest composite score.
        """
        hotspots: List[HotspotFile] = []
        for rec in file_records:
            norm_path = rec.file_path.replace("\\", "/")
            # centrality keys may be full paths; try exact match then basename
            c = centrality.get(norm_path, 0.0)
            if c == 0.0:
                # Fuzzy fallback: match by basename
                base = os.path.basename(norm_path)
                for key, val in centrality.items():
                    if os.path.basename(key) == base:
                        c = val
                        break

            hotspot_score = round(rec.churn_score * (1.0 + c), 4)
            hotspots.append(
                HotspotFile(
                    file_path=rec.file_path,
                    churn_score=rec.churn_score,
                    centrality=round(c, 4),
                    hotspot_score=hotspot_score,
                    commit_count=rec.commit_count,
                    primary_author=rec.primary_author,
                    bus_factor_risk=rec.bus_factor_risk,
                )
            )

        hotspots.sort(key=lambda h: h.hotspot_score, reverse=True)
        return hotspots[:top_n]

    # ------------------------------------------------------------------
    # Step 6 — Author ownership list
    # ------------------------------------------------------------------

    @staticmethod
    def _build_ownership_list(
        raw_ownership: Dict[str, Counter],
        top_n: int = 50,
    ) -> List[AuthorOwnership]:
        """Build per-file author ownership models for the top-N churned files."""
        result: List[AuthorOwnership] = []
        for path, counter in raw_ownership.items():
            total = sum(counter.values()) or 1
            top_author, top_count = counter.most_common(1)[0] if counter else ("", 0)
            result.append(
                AuthorOwnership(
                    file_path=path,
                    primary_author=top_author,
                    ownership_pct=round((top_count / total) * 100.0, 1),
                    contributors=dict(counter),
                )
            )
        # Return sorted by ownership_pct descending, capped at top_n
        result.sort(key=lambda a: a.ownership_pct, reverse=True)
        return result[:top_n]

    # ------------------------------------------------------------------
    # Step 7 — Timeline
    # ------------------------------------------------------------------

    @staticmethod
    def _build_timeline(commits: List[Dict[str, Any]]) -> List[TimelineEntry]:
        """Bin commits into ISO-8601 weekly buckets (week starts Monday)."""

        weekly: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "commit_count": 0,
                "files_changed": set(),
                "authors": set(),
            }
        )

        for commit in commits:
            raw_date = commit.get("date", "")
            if not raw_date:
                continue
            try:
                # Handles ISO-8601 with timezone offset, e.g. 2024-03-15T12:34:56+00:00
                dt = datetime.fromisoformat(raw_date[:19])
                # Find Monday of the week
                monday = dt.date() - timedelta(days=dt.weekday())
                week_key = monday.isoformat()
            except ValueError:
                continue

            bucket = weekly[week_key]
            bucket["commit_count"] += 1
            bucket["authors"].add(commit.get("author", ""))
            for f in commit.get("files", []):
                bucket["files_changed"].add(f["path"])

        entries = [
            TimelineEntry(
                week=week,
                commit_count=data["commit_count"],
                files_changed=len(data["files_changed"]),
                authors=sorted(data["authors"]),
            )
            for week, data in sorted(weekly.items())
        ]
        return entries

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _summary_path(self, repo_name: str, since_days: int) -> str:
        return self.snapshot_store._get_path(
            repo_name, "churn", subkey=f"{since_days}d"
        )

    def _save(self, repo_name: str, since_days: int, summary: ChurnSummary) -> None:
        payload = summary.model_dump()
        payload["_schema_version"] = _SCHEMA_VERSION
        payload["_built_at"] = int(time.time())
        self.snapshot_store.save(repo_name, "churn", payload, subkey=f"{since_days}d")

    def _load_raw(self, repo_name: str, since_days: int) -> Optional[Dict[str, Any]]:
        return self.snapshot_store.load(repo_name, "churn", subkey=f"{since_days}d")
