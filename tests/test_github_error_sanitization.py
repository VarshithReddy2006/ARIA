"""Regression tests for GitHub failure classification and response sanitization.

Verifies that every GitHub failure mode is classified distinctly for operators
while user-visible messages stay generic and never disclose credential state,
repository existence, git stderr, git commands, or exception text.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.github_service import (
    ACCESS_DENIED_MESSAGE,
    GIT_FAILURE_MESSAGE,
    NETWORK_FAILURE_MESSAGE,
    GitHubService,
    GitOperationError,
    RepositoryNotFoundError,
    classify_git_failure,
)
from utils.subprocess_runner import SafeSubprocessError

# Substrings that must never appear in any client-visible message.
FORBIDDEN_SUBSTRINGS = (
    "PAT",
    "GITHUB_TOKEN",
    "Authentication failure",
    "authentication failed",
    "Bearer",
    "Authorization",
    "http.extraHeader",
    "x-access-token",
    "Traceback",
    "git ls-remote",
    "git clone",
    "fatal:",
    "stderr",
)

SAFE_MESSAGES = {ACCESS_DENIED_MESSAGE, NETWORK_FAILURE_MESSAGE, GIT_FAILURE_MESSAGE}


def assert_no_leakage(message: str) -> None:
    """Assert a client-visible message discloses no internal or credential detail."""
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in message, f"leaked {forbidden!r} in {message!r}"
    assert message in SAFE_MESSAGES


def _service(token=None) -> GitHubService:
    return GitHubService(token=token)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr,expected",
    [
        ("remote: Invalid username or password", "invalid_credentials"),
        (
            "fatal: Authentication failed for 'https://github.com/o/r'",
            "invalid_credentials",
        ),
        ("remote: Bad credentials", "invalid_credentials"),
        ("The requested URL returned error: 401", "invalid_credentials"),
        ("remote: Permission denied to user", "permission_denied"),
        ("The requested URL returned error: 403", "permission_denied"),
        ("remote: Repository not found.", "not_found"),
        ("The requested URL returned error: 404", "not_found"),
        ("fatal: could not resolve host: github.com", "network"),
        ("ssh: connect to host github.com port 22: Connection refused", "network"),
        ("error: some other git problem", "git_failure"),
    ],
)
def test_git_failures_are_classified_distinctly(stderr: str, expected: str) -> None:
    assert classify_git_failure(stderr, returncode=128) == expected


def test_timeout_is_classified_as_network() -> None:
    assert classify_git_failure("", returncode=-1, timed_out=True) == "network"


def test_distinct_categories_are_not_collapsed_into_authentication() -> None:
    categories = {
        classify_git_failure("The requested URL returned error: 401", 128),
        classify_git_failure("The requested URL returned error: 403", 128),
        classify_git_failure("remote: Repository not found.", 128),
        classify_git_failure("fatal: could not resolve host: github.com", 128),
        classify_git_failure("error: unknown git problem", 128),
    }
    assert len(categories) == 5


# ---------------------------------------------------------------------------
# Client-visible messages per failure mode
# ---------------------------------------------------------------------------


def _clone_with_stderr(stderr: str, token=None):
    service = _service(token)
    with patch("services.github_service.run_safe_command") as mock_run:
        mock_run.return_value = MagicMock(returncode=128, stderr=stderr, stdout="")
        with pytest.raises(RuntimeError) as exc_info:
            service.clone_repository("https://github.com/owner/repo.git", branch="main")
    return exc_info.value


def test_valid_public_repository_clones_successfully(tmp_path) -> None:
    service = _service()
    with (
        patch("services.github_service.run_safe_command") as mock_run,
        patch("os.path.exists", return_value=False),
        patch("os.makedirs"),
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="HEAD", stderr=""),
            MagicMock(returncode=0, stdout="HEAD", stderr=""),
            MagicMock(returncode=0, stdout="refs/heads/main", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        dest = service.clone_repository(
            "https://github.com/owner/repo.git", branch="main"
        )
    assert "owner_repo" in dest.replace("\\", "/")


def test_nonexistent_repository_returns_generic_access_message() -> None:
    error = _clone_with_stderr("remote: Repository not found.")
    assert isinstance(error, RepositoryNotFoundError)
    assert_no_leakage(str(error))


def test_private_repository_without_permission_returns_generic_message() -> None:
    error = _clone_with_stderr("remote: Permission denied to user", token="ghp_secret")
    assert isinstance(error, RepositoryNotFoundError)
    assert_no_leakage(str(error))


def test_invalid_pat_returns_generic_message() -> None:
    error = _clone_with_stderr(
        "remote: Invalid username or password", token="ghp_invalid_secret"
    )
    assert isinstance(error, RepositoryNotFoundError)
    assert_no_leakage(str(error))


def test_expired_pat_returns_generic_message() -> None:
    error = _clone_with_stderr(
        "fatal: Authentication failed for 'https://github.com/owner/repo.git'",
        token="ghp_expired_secret",
    )
    assert isinstance(error, RepositoryNotFoundError)
    assert_no_leakage(str(error))


def test_github_403_returns_generic_message() -> None:
    error = _clone_with_stderr(
        "The requested URL returned error: 403", token="ghp_secret"
    )
    assert isinstance(error, RepositoryNotFoundError)
    assert_no_leakage(str(error))


def test_github_404_returns_generic_message() -> None:
    error = _clone_with_stderr("The requested URL returned error: 404")
    assert isinstance(error, RepositoryNotFoundError)
    assert_no_leakage(str(error))


def test_access_failures_are_indistinguishable_to_clients() -> None:
    messages = {
        str(_clone_with_stderr("The requested URL returned error: 401", "ghp_x")),
        str(_clone_with_stderr("The requested URL returned error: 403", "ghp_x")),
        str(_clone_with_stderr("remote: Repository not found.", "ghp_x")),
    }
    assert messages == {ACCESS_DENIED_MESSAGE}


def test_network_failure_returns_generic_network_message() -> None:
    error = _clone_with_stderr("fatal: could not resolve host: github.com")
    assert isinstance(error, GitOperationError)
    assert str(error) == NETWORK_FAILURE_MESSAGE
    assert_no_leakage(str(error))


def test_network_timeout_returns_generic_network_message() -> None:
    service = _service(token="ghp_secret")
    with patch("services.github_service.run_safe_command") as mock_run:
        mock_run.side_effect = SafeSubprocessError(
            cmd=["git", "ls-remote", "https://github.com/owner/repo.git", "HEAD"],
            returncode=-1,
            stderr="",
            timed_out=True,
        )
        with pytest.raises(GitOperationError) as exc_info:
            service.clone_repository("https://github.com/owner/repo.git", branch="main")

    assert str(exc_info.value) == NETWORK_FAILURE_MESSAGE
    assert_no_leakage(str(exc_info.value))


def test_git_subprocess_failure_returns_generic_message() -> None:
    service = _service()
    with patch("services.github_service.run_safe_command") as mock_run:
        mock_run.side_effect = SafeSubprocessError(
            cmd=["git", "ls-remote", "https://github.com/owner/repo.git", "HEAD"],
            returncode=127,
            stderr="Executable not found: git",
        )
        with pytest.raises(GitOperationError) as exc_info:
            service.clone_repository("https://github.com/owner/repo.git", branch="main")

    assert str(exc_info.value) == GIT_FAILURE_MESSAGE
    assert_no_leakage(str(exc_info.value))


def test_unexpected_git_error_returns_generic_message() -> None:
    error = _clone_with_stderr("error: an unrecognised git problem occurred")
    assert isinstance(error, GitOperationError)
    assert str(error) == GIT_FAILURE_MESSAGE
    assert_no_leakage(str(error))


def test_clone_step_failure_is_sanitized() -> None:
    service = _service(token="ghp_secret")
    with (
        patch("services.github_service.run_safe_command") as mock_run,
        patch("os.path.exists", return_value=False),
        patch("os.makedirs"),
    ):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="HEAD", stderr=""),
            MagicMock(returncode=0, stdout="HEAD", stderr=""),
            MagicMock(returncode=0, stdout="refs/heads/main", stderr=""),
            MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: Authentication failed for 'https://github.com/owner/repo.git'",
            ),
        ]
        with pytest.raises(RepositoryNotFoundError) as exc_info:
            service.clone_repository("https://github.com/owner/repo.git", branch="main")

    assert_no_leakage(str(exc_info.value))


# ---------------------------------------------------------------------------
# Operator diagnostics are preserved in logs
# ---------------------------------------------------------------------------


def test_operator_logs_retain_full_diagnostics(caplog) -> None:
    service = _service(token="ghp_secret")
    caplog.set_level("ERROR", logger="services.github_service")

    with patch("services.github_service.run_safe_command") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=128,
            stderr="remote: Permission denied to user; error: 403",
            stdout="",
        )
        with pytest.raises(RepositoryNotFoundError):
            service.clone_repository("https://github.com/owner/repo.git", branch="main")

    logged = caplog.text
    assert "category=permission_denied" in logged
    assert "repository=owner/repo" in logged
    assert "exit_code=128" in logged
    assert "credentials_configured=True" in logged
    assert "git ls-remote" in logged
    assert "Permission denied to user" in logged


def test_operator_logs_never_contain_the_raw_token(caplog) -> None:
    service = _service(token="ghp_super_secret_value")
    caplog.set_level("ERROR", logger="services.github_service")

    with patch("services.github_service.run_safe_command") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=128, stderr="remote: Repository not found.", stdout=""
        )
        with pytest.raises(RepositoryNotFoundError):
            service.clone_repository("https://github.com/owner/repo.git", branch="main")

    assert "ghp_super_secret_value" not in caplog.text


# ---------------------------------------------------------------------------
# API-visible responses
# ---------------------------------------------------------------------------


def test_index_endpoint_response_is_sanitized() -> None:
    from fastapi.testclient import TestClient

    from backend.api import app

    client = TestClient(app)

    with patch("backend.routers.repositories.github_service") as mock_gh:
        mock_gh.parse_repo_url.return_value = {"owner": "owner", "repo": "repo"}
        mock_gh.clone_repository.side_effect = RepositoryNotFoundError(
            ACCESS_DENIED_MESSAGE
        )
        response = client.post(
            "/api/index", json={"repo_url": "https://github.com/owner/repo"}
        )

    assert response.status_code == 404
    detail = response.json()["detail"]
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in detail


def test_analyze_stream_error_payload_is_sanitized() -> None:

    import time
    from fastapi.testclient import TestClient

    from backend.api import app

    client = TestClient(app)

    with patch("backend.routers.repositories.github_service") as mock_gh:
        mock_gh.clone_repository.side_effect = RepositoryNotFoundError(
            ACCESS_DENIED_MESSAGE
        )
        response = client.post(
            "/api/v1/analyze",
            json={"url": "https://github.com/owner/repo", "branch": "main"},
        )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert job_id

    # Wait for local thread background worker to record failure
    for _ in range(50):
        status_res = client.get(f"/api/v1/analyze/{job_id}")
        if (
            status_res.status_code == 200
            and status_res.json().get("status") == "failed"
        ):
            break
        time.sleep(0.05)

    data = status_res.json()
    assert data["status"] == "failed"
    err_text = data.get("error", "")
    for forbidden in (
        "PAT",
        "GITHUB_TOKEN",
        "Authentication failure",
        "Bearer",
        "Traceback",
        "fatal:",
    ):
        assert forbidden not in err_text
    assert "Repository not found or access denied." in err_text


def test_pr_health_response_never_exposes_token_material() -> None:
    from fastapi.testclient import TestClient

    from backend.api import app

    client = TestClient(app)
    with patch(
        "services.github_service.GitHubConfig.load_token",
        return_value="ghp_secret_value",
    ):
        response = client.get("/api/pr/health")

    assert response.status_code == 200
    body = response.json()
    assert "ghp_secret_value" not in json_dumps(body)
    assert body["github_token_prefix"] in ("configured", "missing")


def json_dumps(value) -> str:
    import json

    return json.dumps(value)
