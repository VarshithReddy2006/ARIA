"""Unit tests for GitHubService safe subprocess execution and credential handling."""

from unittest.mock import patch, MagicMock
import pytest
from services.github_service import GitHubService
from utils.subprocess_runner import CLONE_TIMEOUT, SHORT_GIT_TIMEOUT, INSPECTION_TIMEOUT


def test_github_service_credentials_not_in_url() -> None:
    """Verify PAT token is NOT embedded into the remote URL string."""
    service = GitHubService(token="ghp_test_secret_pat_999")
    repo_url = "https://github.com/myorg/myrepo.git"

    with (
        patch("services.github_service.run_safe_command") as mock_run,
        patch("os.path.exists", return_value=False),
        patch("os.path.isdir", return_value=True),
        patch("os.makedirs"),
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="HEAD"),  # public check
            MagicMock(returncode=0, stdout="HEAD"),  # diagnostics check
            MagicMock(returncode=0, stdout="refs/heads/main"),  # branch check
            MagicMock(returncode=0, stdout=""),  # clone
            MagicMock(
                returncode=0, stdout="0123456789abcdef0123456789abcdef01234567"
            ),  # rev-parse HEAD
        ]

        service.clone_repository(repo_url, branch="main")

        # Check call arguments passed to run_safe_command
        for call_item in mock_run.call_args_list:
            args, kwargs = call_item
            cmd = args[0]
            # Ensure token is never inside any command string/URL
            for arg in cmd:
                assert "ghp_test_secret_pat_999" not in arg

            # Check secrets parameter passed for redaction
            secrets = kwargs.get("secrets", [])
            assert "ghp_test_secret_pat_999" in secrets

            # For private/authenticated operations, check GIT_CONFIG env headers
            env = kwargs.get("env", {})
            if env:
                assert env.get("GIT_CONFIG_KEY_0") == "http.extraHeader"
                assert "Authorization: Basic " in env.get("GIT_CONFIG_VALUE_0", "")


def test_github_service_cloning_failure_redacts_secrets() -> None:
    """Verify clone failure error messages redact PAT tokens."""
    service = GitHubService(token="ghp_secret_token_abc123")
    repo_url = "https://github.com/myorg/private-repo.git"

    with patch("services.github_service.run_safe_command") as mock_run:
        # Public check fails, auth check fails (res.stderr clean/redacted)
        from utils.subprocess_runner import redact_text

        raw_stderr = "fatal: authentication failed for ghp_secret_token_abc123"
        clean_stderr = redact_text(raw_stderr, ["ghp_secret_token_abc123"])

        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="not public", stdout=""),
            MagicMock(returncode=128, stderr=clean_stderr, stdout=""),
        ]

        with pytest.raises(RuntimeError) as exc_info:
            service.clone_repository(repo_url, branch="main")

        # The client-visible message carries no git stderr at all, so the token
        # cannot appear in any form. Redaction is still asserted for logs by
        # tests/test_github_error_sanitization.py.
        err_msg = str(exc_info.value)
        assert "ghp_secret_token_abc123" not in err_msg
        assert err_msg == "Repository not found or access denied."


def test_github_service_uses_operation_timeouts() -> None:
    """Verify that clone_repository enforces operation timeouts (SHORT_GIT_TIMEOUT, CLONE_TIMEOUT)."""
    service = GitHubService(token=None)
    repo_url = "https://github.com/owner/repo.git"

    with (
        patch("services.github_service.run_safe_command") as mock_run,
        patch("os.path.exists", return_value=False),
        patch("os.path.isdir", return_value=True),
        patch("os.makedirs"),
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="HEAD"),  # public check
            MagicMock(returncode=0, stdout="HEAD"),  # diagnostics check
            MagicMock(returncode=0, stdout="refs/heads/main"),  # branch check
            MagicMock(returncode=0, stdout=""),  # clone
            MagicMock(
                returncode=0, stdout="0123456789abcdef0123456789abcdef01234567"
            ),  # rev-parse HEAD
        ]

        service.clone_repository(repo_url, branch="main")

        # Verify timeouts
        assert mock_run.call_args_list[0][1]["timeout"] == SHORT_GIT_TIMEOUT
        assert mock_run.call_args_list[1][1]["timeout"] == SHORT_GIT_TIMEOUT
        assert mock_run.call_args_list[2][1]["timeout"] == INSPECTION_TIMEOUT
        assert mock_run.call_args_list[3][1]["timeout"] == CLONE_TIMEOUT
        assert mock_run.call_args_list[4][1]["timeout"] == SHORT_GIT_TIMEOUT


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://attacker.com/github.com/org/repo",
        "https://evil.test/github.com/org/repo",
        "https://anything/github.com/org/repo",
    ],
)
def test_parse_repo_url_rejects_attacker_controlled_hosts(repo_url: str) -> None:
    service = GitHubService(token="test-token")
    with pytest.raises(ValueError, match="Invalid GitHub repository URL"):
        service.parse_repo_url(repo_url)


def test_parse_repo_url_canonicalizes_valid_github_url() -> None:
    service = GitHubService(token=None)
    assert service.parse_repo_url("https://github.com/org/repo.git") == {
        "owner": "org",
        "repo": "repo",
    }


def test_rejected_remote_never_runs_authenticated_git_command() -> None:
    service = GitHubService(token="test-token")
    with patch("services.github_service.run_safe_command") as mock_run:
        with pytest.raises(Exception):
            service.clone_repository("https://attacker.com/github.com/org/repo")
    mock_run.assert_not_called()


def test_extract_source_files_rejects_symlinks_and_oversized_files(tmp_path) -> None:
    service = GitHubService(token=None)
    normal = tmp_path / "normal.py"
    normal.write_text("print('safe')", encoding="utf-8")
    oversized = tmp_path / "oversized.py"
    oversized.write_bytes(b"x" * (service._MAX_SOURCE_FILE_SIZE_BYTES + 1))

    target = tmp_path / "target.py"
    target.write_text("print('target')", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this test environment")

    files = service.extract_source_files(str(tmp_path))
    # target.py is a regular file (not a symlink) so it passes the safety filter.
    # Only linked.py (symlink) and oversized.py (exceeds size limit) are excluded.
    paths = sorted(f["path"] for f in files)
    assert paths == ["normal.py", "target.py"]


def test_extract_source_files_rejects_symlink_escaping_repository(tmp_path) -> None:
    service = GitHubService(token=None)
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 'outside'", encoding="utf-8")
    escaped_link = repository / "escaped.py"
    try:
        escaped_link.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links are unavailable in this test environment")

    assert service.extract_source_files(str(repository)) == []


def test_source_file_guard_rejects_a_symlink_before_reading(tmp_path) -> None:
    service = GitHubService(token=None)
    source = tmp_path / "source.py"
    source.write_text("print('safe')", encoding="utf-8")

    with patch("services.github_service.os.path.islink", return_value=True):
        assert service._safe_source_file(str(source), str(tmp_path)) is False


def test_clone_repository_includes_low_speed_protection() -> None:
    service = GitHubService(token=None)
    with (
        patch("services.github_service.run_safe_command") as mock_run,
        patch("os.path.exists", return_value=False),
        patch("os.path.isdir", return_value=True),
        patch("os.makedirs"),
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="HEAD"),
            MagicMock(returncode=0, stdout="HEAD"),
            MagicMock(returncode=0, stdout="refs/heads/main"),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="0123456789abcdef0123456789abcdef01234567"),
        ]
        service.clone_repository("https://github.com/owner/repo.git", branch="main")

        clone_cmd = mock_run.call_args_list[3][0][0]
        assert "-c" in clone_cmd
        assert "http.lowSpeedLimit=1000" in clone_cmd
        assert "http.lowSpeedTime=20" in clone_cmd


def test_iter_source_files_yields_incrementally(tmp_path) -> None:
    service = GitHubService(token=None)
    (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
    (tmp_path / "b.js").write_text("console.log('b')", encoding="utf-8")
    (tmp_path / "c.png").write_bytes(b"\x89PNG")

    items = list(service.iter_source_files(str(tmp_path)))
    paths = sorted(i["path"] for i in items)
    assert paths == ["a.py", "b.js"]
    assert items[0]["content"] in ("print('a')", "console.log('b')")


def test_iter_source_files_enforces_byte_limit(tmp_path) -> None:
    service = GitHubService(token=None)
    (tmp_path / "big.py").write_text("x" * 500, encoding="utf-8")

    with pytest.raises(
        ValueError, match="Repository exceeds maximum allowed source size"
    ):
        list(service.iter_source_files(str(tmp_path), max_total_bytes=100))


def test_iter_source_files_enforces_file_count_limit(tmp_path) -> None:
    service = GitHubService(token=None)
    (tmp_path / "f1.py").write_text("1", encoding="utf-8")
    (tmp_path / "f2.py").write_text("2", encoding="utf-8")

    with pytest.raises(
        ValueError, match="Repository exceeds maximum allowed file count"
    ):
        list(service.iter_source_files(str(tmp_path), max_files=1))
