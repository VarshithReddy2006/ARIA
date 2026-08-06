"""Tests for utils.subprocess_runner — safe subprocess execution module."""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
import pytest

from utils.subprocess_runner import (
    run_safe_command,
    SafeSubprocessError,
    redact_text,
    DEFAULT_TIMEOUT,
    SHORT_GIT_TIMEOUT,
    INSPECTION_TIMEOUT,
    CLONE_TIMEOUT,
    HISTORY_ANALYSIS_TIMEOUT,
)


class TestSubprocessRunner:
    """Test suite for safe subprocess runner functionality."""

    def test_successful_execution(self) -> None:
        """Test executing a basic command successfully."""
        cmd = [sys.executable, "-c", "print('hello world')"]
        res = run_safe_command(cmd, timeout=10.0)
        assert res.returncode == 0
        assert res.stdout.strip() == "hello world"

    def test_non_zero_exit_code_without_check(self) -> None:
        """Test non-zero exit code without check=True returns CompletedProcess."""
        cmd = [sys.executable, "-c", "import sys; print('err msg', file=sys.stderr); sys.exit(42)"]
        res = run_safe_command(cmd, check=False)
        assert res.returncode == 42
        assert "err msg" in res.stderr

    def test_non_zero_exit_code_with_check(self) -> None:
        """Test check=True raises SafeSubprocessError on non-zero exit code."""
        cmd = [sys.executable, "-c", "import sys; print('fatal error', file=sys.stderr); sys.exit(1)"]
        with pytest.raises(SafeSubprocessError) as exc_info:
            run_safe_command(cmd, check=True)

        err = exc_info.value
        assert err.returncode == 1
        assert "fatal error" in err.stderr
        assert err.timed_out is False

    def test_timeout_handling(self) -> None:
        """Test that execution times out and raises SafeSubprocessError with timed_out=True."""
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        with pytest.raises(SafeSubprocessError) as exc_info:
            run_safe_command(cmd, timeout=0.2)

        err = exc_info.value
        assert err.timed_out is True
        assert err.returncode == -1
        assert "timed out after 0.2s" in str(err)

    def test_missing_executable(self) -> None:
        """Test executing a non-existent binary raises SafeSubprocessError."""
        cmd = ["non_existent_binary_999999", "--version"]
        with pytest.raises(SafeSubprocessError) as exc_info:
            run_safe_command(cmd)

        err = exc_info.value
        assert err.returncode == -1
        assert "Executable not found" in err.stderr or "Executable not found" in str(err)

    def test_secret_redaction_in_output_and_exceptions(self) -> None:
        """Test that secret tokens are redacted from stdout, stderr, and exception messages."""
        secret_token = "ghp_super_secret_pat_token_12345"
        cmd = [
            sys.executable,
            "-c",
            f"import sys; print('Output with {secret_token}'); print('Error with {secret_token}', file=sys.stderr); sys.exit(1)",
        ]

        with pytest.raises(SafeSubprocessError) as exc_info:
            run_safe_command(cmd, secrets=[secret_token], check=True)

        err = exc_info.value
        assert secret_token not in err.stdout
        assert secret_token not in err.stderr
        assert secret_token not in str(err)
        assert "[REDACTED]" in err.stdout
        assert "[REDACTED]" in err.stderr
        assert "[REDACTED]" in str(err)

    def test_environment_injection(self) -> None:
        """Test that hardened Git environment variables and custom env variables are injected."""
        cmd = [
            sys.executable,
            "-c",
            "import os, json; print(json.dumps(dict(os.environ)))",
        ]
        res = run_safe_command(cmd, env={"CUSTOM_TEST_VAR": "test_val"})
        assert res.returncode == 0

        env_out = res.stdout.strip()
        assert "GIT_TERMINAL_PROMPT" in env_out
        assert '"GIT_TERMINAL_PROMPT": "0"' in env_out
        assert "CUSTOM_TEST_VAR" in env_out
        assert '"CUSTOM_TEST_VAR": "test_val"' in env_out

    def test_reject_non_list_commands(self) -> None:
        """Test that non-sequence commands (e.g. raw string) are rejected to prevent shell execution."""
        with pytest.raises(TypeError):
            run_safe_command("echo hello")  # type: ignore

    def test_redact_text_helper(self) -> None:
        """Test redact_text utility function."""
        secret = "secret123"
        text = f"URL https://{secret}@github.com/repo.git"
        redacted = redact_text(text, [secret])
        assert redacted == "URL https://[REDACTED]@github.com/repo.git"

    def test_concurrent_subprocess_execution(self) -> None:
        """Test running multiple safe subprocesses concurrently."""
        def _run_worker(idx: int) -> int:
            cmd = [sys.executable, "-c", f"print({idx})"]
            res = run_safe_command(cmd, timeout=5.0)
            return int(res.stdout.strip())

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_run_worker, i) for i in range(10)]
            results = [f.result() for f in futures]

        assert results == list(range(10))

    def test_timeout_categories(self) -> None:
        """Verify timeout category values."""
        assert SHORT_GIT_TIMEOUT == 15.0
        assert INSPECTION_TIMEOUT == 30.0
        assert HISTORY_ANALYSIS_TIMEOUT == 120.0
        assert CLONE_TIMEOUT == 300.0
        assert DEFAULT_TIMEOUT == 30.0
