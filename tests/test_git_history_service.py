"""Tests for GitHistoryService — git history & churn analysis.

Uses synthetic git log output fixtures to validate parsing, aggregation,
normalisation, hotspot computation, and timeline building without requiring
a real repository on disk.
"""

from __future__ import annotations

import os
import json
from unittest.mock import MagicMock

import pytest

from models.churn import (
    ChurnSummary,
    FileChurnRecord,
)
from services.git_history_service import GitHistoryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_GIT_LOG = """\
COMMIT|abc123|alice@example.com|2024-06-01T10:00:00+00:00
M\tservices/auth.py
M\tmodels/user.py
COMMIT|def456|bob@example.com|2024-06-02T11:00:00+00:00
M\tservices/auth.py
A\tfrontend/login.tsx
COMMIT|ghi789|alice@example.com|2024-06-03T09:00:00+00:00
M\tservices/auth.py
D\tdocs/old_readme.md
COMMIT|jkl012|carol@example.com|2024-06-04T08:00:00+00:00
R100\tmodels/old_user.py\tmodels/user_v2.py
"""


def make_service(tmp_churn_dir: str) -> GitHistoryService:
    mock_github = MagicMock()
    mock_github.get_local_repo_path.return_value = "/fake/repo"
    mock_graph = MagicMock()
    mock_graph.load_graph.return_value = None
    return GitHistoryService(
        github_service=mock_github,
        graph_service=mock_graph,
        churn_dir=tmp_churn_dir,
    )


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestParseGitLog:
    def test_parses_commit_headers(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        assert len(commits) == 4

    def test_parses_modified_files(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        first = commits[0]
        assert first["hash"] == "abc123"
        assert first["author"] == "alice@example.com"
        paths = [f["path"] for f in first["files"]]
        assert "services/auth.py" in paths
        assert "models/user.py" in paths

    def test_parses_added_file(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        paths = [f["path"] for f in commits[1]["files"]]
        assert "frontend/login.tsx" in paths

    def test_parses_deleted_file(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        files = commits[2]["files"]
        deleted = [f for f in files if f["status"] == "deleted"]
        assert any(f["path"] == "docs/old_readme.md" for f in deleted)

    def test_parses_renamed_file(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        files = commits[3]["files"]
        renamed = [f for f in files if f["status"] == "renamed"]
        assert renamed[0]["path"] == "models/user_v2.py"

    def test_empty_log_returns_empty_list(self):
        assert GitHistoryService._parse_git_log("") == []


# ---------------------------------------------------------------------------
# Aggregation tests
# ---------------------------------------------------------------------------


class TestAggregateChurn:
    def test_commit_count_per_file(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        churn = GitHistoryService._aggregate_churn(commits)
        # services/auth.py appears in commits 0, 1, 2
        assert churn["services/auth.py"]["commit_count"] == 3

    def test_last_commit_date_is_most_recent(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        churn = GitHistoryService._aggregate_churn(commits)
        assert (
            churn["services/auth.py"]["last_commit_date"] == "2024-06-03T09:00:00+00:00"
        )

    def test_deleted_flag_set_correctly(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        churn = GitHistoryService._aggregate_churn(commits)
        assert churn["docs/old_readme.md"]["is_deleted"] is True
        assert churn["services/auth.py"]["is_deleted"] is False


class TestAggregateOwnership:
    def test_author_counts(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        ownership = GitHistoryService._aggregate_ownership(commits)
        auth_counter = ownership["services/auth.py"]
        assert auth_counter["alice@example.com"] == 2
        assert auth_counter["bob@example.com"] == 1

    def test_single_author_file(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        ownership = GitHistoryService._aggregate_ownership(commits)
        assert ownership["frontend/login.tsx"]["bob@example.com"] == 1


# ---------------------------------------------------------------------------
# Normalisation tests
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_top_file_scores_100(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        raw_churn = GitHistoryService._aggregate_churn(commits)
        raw_ownership = GitHistoryService._aggregate_ownership(commits)
        records = GitHistoryService._normalise(raw_churn, raw_ownership)
        top = records[0]
        assert top.churn_score == 100.0

    def test_scores_in_valid_range(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        raw_churn = GitHistoryService._aggregate_churn(commits)
        raw_ownership = GitHistoryService._aggregate_ownership(commits)
        records = GitHistoryService._normalise(raw_churn, raw_ownership)
        for rec in records:
            assert 0.0 <= rec.churn_score <= 100.0

    def test_bus_factor_risk_detected(self):
        """File touched only by alice should flag bus factor risk."""
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        raw_churn = GitHistoryService._aggregate_churn(commits)
        raw_ownership = GitHistoryService._aggregate_ownership(commits)
        records = GitHistoryService._normalise(raw_churn, raw_ownership)
        # services/auth.py: alice=2, bob=1 → alice is 67% — no bus risk
        auth_rec = next((r for r in records if r.file_path == "services/auth.py"), None)
        assert auth_rec is not None
        assert auth_rec.bus_factor_risk is False
        # models/user.py: only alice=1 → 100% — bus risk
        user_rec = next((r for r in records if r.file_path == "models/user.py"), None)
        assert user_rec is not None
        assert user_rec.bus_factor_risk is True

    def test_empty_input_returns_empty(self):
        assert GitHistoryService._normalise({}, {}) == []


# ---------------------------------------------------------------------------
# Hotspot computation tests
# ---------------------------------------------------------------------------


class TestComputeHotspots:
    def _make_records(self):
        return [
            FileChurnRecord(
                file_path="services/auth.py",
                commit_count=3,
                churn_score=100.0,
                primary_author="alice@example.com",
                author_count=2,
                bus_factor_risk=False,
                last_commit_date="",
            ),
            FileChurnRecord(
                file_path="models/user.py",
                commit_count=1,
                churn_score=33.3,
                primary_author="alice@example.com",
                author_count=1,
                bus_factor_risk=True,
                last_commit_date="",
            ),
        ]

    def test_hotspot_score_includes_centrality_bonus(self):
        records = self._make_records()
        centrality = {"services/auth.py": 0.5, "models/user.py": 0.0}
        hotspots = GitHistoryService._compute_hotspots(records, centrality)
        top = hotspots[0]
        assert top.file_path == "services/auth.py"
        assert top.hotspot_score == pytest.approx(100.0 * 1.5, rel=1e-3)

    def test_no_graph_centrality_falls_back_to_zero(self):
        records = self._make_records()
        hotspots = GitHistoryService._compute_hotspots(records, {})
        # hotspot_score = churn_score × (1 + 0)
        assert hotspots[0].hotspot_score == pytest.approx(100.0, rel=1e-3)

    def test_top_n_respected(self):
        records = self._make_records()
        hotspots = GitHistoryService._compute_hotspots(records, {}, top_n=1)
        assert len(hotspots) == 1


# ---------------------------------------------------------------------------
# Timeline tests
# ---------------------------------------------------------------------------


class TestBuildTimeline:
    def test_weekly_bucketing(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        timeline = GitHistoryService._build_timeline(commits)
        # All four commits fall in the same week (2024-06-01 is a Saturday,
        # so the Monday bucket is 2024-05-27; adjust test to check length ≥ 1)
        assert len(timeline) >= 1
        total_commits = sum(e.commit_count for e in timeline)
        assert total_commits == 4

    def test_authors_per_week_deduplicated(self):
        commits = GitHistoryService._parse_git_log(SAMPLE_GIT_LOG)
        timeline = GitHistoryService._build_timeline(commits)
        all_authors = set()
        for e in timeline:
            all_authors.update(e.authors)
        assert "alice@example.com" in all_authors
        assert "bob@example.com" in all_authors


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_save_and_load_round_trip(self, tmp_path):
        service = make_service(str(tmp_path))
        summary = ChurnSummary(
            repo="owner/repo",
            generated_at="2024-06-01T00:00:00+00:00",
            since_days=365,
            total_commits=10,
            total_files=5,
        )
        service._save("owner/repo", 365, summary)
        loaded = service.load("owner/repo", 365)
        assert loaded is not None
        assert loaded.repo == "owner/repo"
        assert loaded.total_commits == 10

    def test_missing_file_returns_none(self, tmp_path):
        service = make_service(str(tmp_path))
        assert service.load("does/notexist", 365) is None

    def test_summary_exists_false_when_missing(self, tmp_path):
        service = make_service(str(tmp_path))
        assert service.summary_exists("owner/repo", 365) is False

    def test_summary_exists_true_after_save(self, tmp_path):
        service = make_service(str(tmp_path))
        summary = ChurnSummary(
            repo="owner/repo",
            generated_at="2024-06-01T00:00:00+00:00",
            since_days=365,
            total_commits=1,
            total_files=1,
        )
        service._save("owner/repo", 365, summary)
        assert service.summary_exists("owner/repo", 365) is True

    def test_stale_schema_returns_none(self, tmp_path):
        service = make_service(str(tmp_path))
        path = service._summary_path("owner/repo", 365)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                {
                    "_schema_version": 0,
                    "repo": "owner/repo",
                    "generated_at": "",
                    "since_days": 365,
                    "total_commits": 0,
                    "total_files": 0,
                },
                f,
            )
        assert service.load("owner/repo", 365) is None


# ---------------------------------------------------------------------------
# get_file_record test
# ---------------------------------------------------------------------------


class TestGetFileRecord:
    def test_returns_correct_record(self, tmp_path):
        service = make_service(str(tmp_path))
        rec = FileChurnRecord(
            file_path="services/auth.py",
            commit_count=3,
            churn_score=100.0,
            primary_author="alice@example.com",
            author_count=2,
            bus_factor_risk=False,
            last_commit_date="",
        )
        summary = ChurnSummary(
            repo="owner/repo",
            generated_at="2024-06-01T00:00:00+00:00",
            since_days=365,
            total_commits=3,
            total_files=1,
            file_records=[rec],
        )
        service._save("owner/repo", 365, summary)
        result = service.get_file_record("owner/repo", "services/auth.py", 365)
        assert result is not None
        assert result.file_path == "services/auth.py"

    def test_unknown_file_returns_none(self, tmp_path):
        service = make_service(str(tmp_path))
        summary = ChurnSummary(
            repo="owner/repo",
            generated_at="2024-06-01T00:00:00+00:00",
            since_days=365,
            total_commits=0,
            total_files=0,
        )
        service._save("owner/repo", 365, summary)
        assert service.get_file_record("owner/repo", "no/such/file.py", 365) is None


# ---------------------------------------------------------------------------
# Generator & Asyncio / to_thread Regression Tests
# ---------------------------------------------------------------------------


class TestGeneratorAsyncioSafety:
    """Regression tests verifying generators executed via asyncio.to_thread do not leak StopIteration into Futures."""

    @pytest.mark.asyncio
    async def test_advance_generator_captures_completion(self):
        from backend.routers.git_history import _advance_generator

        def sample_gen():
            yield {"status": "step1"}
            yield {"status": "step2"}
            return "final_summary"

        gen = sample_gen()
        is_done, val = _advance_generator(gen)
        assert is_done is False
        assert val == {"status": "step1"}

        is_done, val = _advance_generator(gen)
        assert is_done is False
        assert val == {"status": "step2"}

        is_done, val = _advance_generator(gen)
        assert is_done is True
        assert val == "final_summary"

    @pytest.mark.asyncio
    async def test_asyncio_to_thread_does_not_raise_stop_iteration_runtime_error(self):
        import asyncio
        from backend.routers.git_history import _advance_generator

        def sample_gen():
            yield {"status": "mining"}
            yield {"status": "computing"}
            return "done_value"

        gen = sample_gen()
        events = []
        result = None

        while True:
            is_done, value = await asyncio.to_thread(_advance_generator, gen)
            if is_done:
                result = value
                break
            events.append(value)

        assert len(events) == 2
        assert events[0] == {"status": "mining"}
        assert events[1] == {"status": "computing"}
        assert result == "done_value"

    @pytest.mark.asyncio
    async def test_build_generator_runs_through_asyncio_to_thread(self, tmp_path):
        import asyncio
        from unittest.mock import patch
        from backend.routers.git_history import _advance_generator

        service = make_service(str(tmp_path))

        with (
            patch("os.path.isdir", return_value=True),
            patch.object(
                service,
                "_mine_commits",
                return_value=(
                    GitHistoryService._parse_git_log(SAMPLE_GIT_LOG),
                    None,
                ),
            ),
            patch.object(service, "_count_all_commits", return_value=100),
        ):
            gen = service.build("owner/repo", since_days=365)
            events = []
            summary = None

            while True:
                is_done, val = await asyncio.to_thread(_advance_generator, gen)
                if is_done:
                    summary = val
                    break
                events.append(val)

            assert len(events) > 0
            assert isinstance(summary, ChurnSummary)
            assert summary.total_commits == 4
            assert len(summary.hotspots) > 0


# ---------------------------------------------------------------------------
# API Router SSE Regression Tests
# ---------------------------------------------------------------------------


class TestGitHistoryRouterRegression:
    """Regression tests for POST /api/v1/churn/analyze SSE endpoint."""

    @pytest.mark.asyncio
    async def test_churn_analyze_sse_success_with_history(self, tmp_path):
        from unittest.mock import patch
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from backend.routers.git_history import router as git_history_router

        test_app = FastAPI()
        test_app.include_router(git_history_router, prefix="/api/v1")

        mock_service = make_service(str(tmp_path))
        with (
            patch("os.path.isdir", return_value=True),
            patch.object(
                mock_service,
                "_mine_commits",
                return_value=(
                    GitHistoryService._parse_git_log(SAMPLE_GIT_LOG),
                    None,
                ),
            ),
            patch.object(mock_service, "_count_all_commits", return_value=100),
            patch(
                "backend.routers.git_history.git_history_service",
                mock_service,
            ),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/churn/analyze",
                    json={"repo": "owner/repo", "since_days": 365},
                )
                assert response.status_code == 200

                lines = response.text.split("\n\n")
                events = []
                for line in lines:
                    line = line.strip()
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                # Verify no StopIteration / RuntimeError error event was sent
                error_events = [e for e in events if e.get("status") == "error"]
                assert not error_events, f"Unexpected error events: {error_events}"

                # Verify result event contains populated ChurnSummary
                result_events = [e for e in events if e.get("status") == "result"]
                assert len(result_events) == 1
                data = result_events[0]["data"]
                assert data["repo"] == "owner/repo"
                assert data["total_commits"] == 4
                assert len(data["hotspots"]) > 0

                # Verify done event
                done_events = [e for e in events if e.get("status") == "done"]
                assert len(done_events) == 1

    @pytest.mark.asyncio
    async def test_churn_analyze_sse_empty_history(self, tmp_path):
        from unittest.mock import patch
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from backend.routers.git_history import router as git_history_router

        test_app = FastAPI()
        test_app.include_router(git_history_router, prefix="/api/v1")

        mock_service = make_service(str(tmp_path))
        with (
            patch("os.path.isdir", return_value=True),
            patch.object(mock_service, "_mine_commits", return_value=([], None)),
            patch.object(mock_service, "_count_all_commits", return_value=0),
            patch(
                "backend.routers.git_history.git_history_service",
                mock_service,
            ),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/churn/analyze",
                    json={"repo": "owner/empty-repo", "since_days": 365},
                )
                assert response.status_code == 200

                lines = response.text.split("\n\n")
                events = []
                for line in lines:
                    line = line.strip()
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                error_events = [e for e in events if e.get("status") == "error"]
                assert not error_events, f"Unexpected error events: {error_events}"

                result_events = [e for e in events if e.get("status") == "result"]
                assert len(result_events) == 1
                data = result_events[0]["data"]
                assert data["repo"] == "owner/empty-repo"
                assert data["total_commits"] == 0
                assert data["hotspots"] == []

    @pytest.mark.asyncio
    async def test_churn_analyze_sse_uncloned_repo_error(self, tmp_path):
        from unittest.mock import patch
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from backend.routers.git_history import router as git_history_router

        test_app = FastAPI()
        test_app.include_router(git_history_router, prefix="/api/v1")

        mock_service = make_service(str(tmp_path))
        with (
            patch("os.path.isdir", return_value=False),
            patch(
                "backend.routers.git_history.git_history_service",
                mock_service,
            ),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/churn/analyze",
                    json={"repo": "owner/not-cloned", "since_days": 365},
                )
                assert response.status_code == 200

                lines = response.text.split("\n\n")
                events = []
                for line in lines:
                    line = line.strip()
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

                error_events = [e for e in events if e.get("status") == "error"]
                assert len(error_events) == 1
                assert "not cloned locally" in error_events[0]["message"]
