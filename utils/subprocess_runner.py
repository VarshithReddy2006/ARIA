"""Safe subprocess execution utility.

Provides robust, secure, and standardized process execution across the platform.
Features:
- Mandatory non-shell execution (`shell=False` enforced)
- Enforced operation-specific timeouts
- Automated secret redaction in logs, outputs, and exceptions
- Non-interactive environment hardening for Git and external tools
- Structured error handling via SafeSubprocessError
"""

import logging
import os
import subprocess
import threading
from typing import Dict, Optional, Sequence, Union

logger = logging.getLogger(__name__)

# Standard timeout categories (in seconds)
SHORT_GIT_TIMEOUT = 15.0
INSPECTION_TIMEOUT = 30.0
HISTORY_ANALYSIS_TIMEOUT = 120.0
CLONE_TIMEOUT = 300.0
DEFAULT_TIMEOUT = 30.0

# Bounded output capture limit (16 KiB per stream to keep memory low on 512MB instances)
DEFAULT_MAX_CAPTURE_BYTES = 16384

# Non-interactive Git environment overrides
SAFE_GIT_ENV: Dict[str, str] = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "GCM_INTERACTIVE": "never",
    "GIT_CONFIG_NOSYSTEM": "1",
    "LC_ALL": "C",
}


class SafeSubprocessError(RuntimeError):
    """Raised when a safe subprocess execution fails or times out."""

    def __init__(
        self,
        cmd: Sequence[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        message: Optional[str] = None,
    ) -> None:
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out

        if message is None:
            if timed_out:
                message = f"Command '{' '.join(self.cmd)}' timed out."
            else:
                message = f"Command '{' '.join(self.cmd)}' failed with exit code {returncode}: {stderr.strip()}"
        super().__init__(message)


def redact_text(text: str, secrets: Sequence[str]) -> str:
    """Redacts all specified secrets from text."""
    if not text or not secrets:
        return text
    redacted = text
    for secret in secrets:
        if secret and len(secret) > 0:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _drain_pipe_bounded(pipe, max_bytes: int = DEFAULT_MAX_CAPTURE_BYTES) -> bytes:
    """Drain an OS pipe to completion while retaining at most max_bytes in memory.

    Discards any trailing data once max_bytes is reached to prevent high heap usage,
    while still reading to EOF to prevent the child process from blocking on full OS pipe buffers.
    """
    if pipe is None:
        return b""
    chunks = []
    total_len = 0
    try:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            if total_len < max_bytes:
                to_take = min(len(chunk), max_bytes - total_len)
                chunks.append(chunk[:to_take])
                total_len += to_take
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass
    return b"".join(chunks)


def run_safe_command(
    cmd: Sequence[str],
    *,
    cwd: Optional[Union[str, os.PathLike]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    env: Optional[Dict[str, str]] = None,
    secrets: Sequence[str] = (),
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    max_output_length: int = 10000,
    max_capture_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
) -> subprocess.CompletedProcess:
    """Executes a subprocess safely with mandatory timeout, non-shell execution, and bounded output memory.

    Args:
        cmd: Command and arguments list. Must be a sequence of strings.
        cwd: Directory in which to execute the command.
        timeout: Execution timeout in seconds.
        env: Additional environment variables to set.
        secrets: List of sensitive strings to redact from logs, errors, and output.
        check: If True, raises SafeSubprocessError on non-zero exit code.
        capture_output: If True, capture stdout and stderr up to max_capture_bytes.
        text: If True, decode output as utf-8 text.
        max_output_length: Maximum length of stdout/stderr kept in exceptions.
        max_capture_bytes: Maximum bytes captured per stream (default 16 KiB).

    Returns:
        subprocess.CompletedProcess instance with sanitized stdout/stderr.

    Raises:
        SafeSubprocessError: If execution times out, executable is missing, or check=True fails.
    """
    if not isinstance(cmd, (list, tuple)):
        raise TypeError(
            "Command must be a list or tuple of strings (non-shell execution)."
        )

    cmd_list = [str(arg) for arg in cmd]

    # Build hardened environment
    merged_env = dict(os.environ)
    merged_env.update(SAFE_GIT_ENV)
    if env:
        merged_env.update(env)

    stdout_buf = []
    stderr_buf = []
    out_thread = None
    err_thread = None

    try:
        proc = subprocess.Popen(
            cmd_list,
            cwd=cwd,
            shell=False,  # Strictly non-shell execution
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            env=merged_env,
        )
    except FileNotFoundError as exc:
        safe_cmd = [redact_text(arg, secrets) for arg in cmd_list]
        raise SafeSubprocessError(
            cmd=safe_cmd,
            returncode=-1,
            stdout="",
            stderr=f"Executable not found: {exc.filename}",
            timed_out=False,
            message=f"Executable not found for command: {' '.join(safe_cmd)}",
        ) from exc
    except Exception as exc:
        safe_cmd = [redact_text(arg, secrets) for arg in cmd_list]
        raise SafeSubprocessError(
            cmd=safe_cmd,
            returncode=-1,
            stdout="",
            stderr=str(exc),
            timed_out=False,
            message=f"Failed to execute command '{' '.join(safe_cmd)}': {exc}",
        ) from exc

    if capture_output:
        out_thread = threading.Thread(
            target=lambda: stdout_buf.append(
                _drain_pipe_bounded(proc.stdout, max_capture_bytes)
            ),
            daemon=True,
        )
        err_thread = threading.Thread(
            target=lambda: stderr_buf.append(
                _drain_pipe_bounded(proc.stderr, max_capture_bytes)
            ),
            daemon=True,
        )
        out_thread.start()
        err_thread.start()

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass

        if out_thread:
            out_thread.join(timeout=1.0)
        if err_thread:
            err_thread.join(timeout=1.0)

        stdout_raw = stdout_buf[0] if stdout_buf else b""
        stderr_raw = stderr_buf[0] if stderr_buf else b""
        stdout_str = (
            redact_text(stdout_raw.decode("utf-8", errors="replace"), secrets)
            if text
            else ""
        )
        stderr_str = (
            redact_text(stderr_raw.decode("utf-8", errors="replace"), secrets)
            if text
            else ""
        )
        safe_cmd = [redact_text(arg, secrets) for arg in cmd_list]
        raise SafeSubprocessError(
            cmd=safe_cmd,
            returncode=-1,
            stdout=stdout_str[:max_output_length],
            stderr=stderr_str[:max_output_length],
            timed_out=True,
            message=f"Command '{' '.join(safe_cmd)}' timed out after {timeout}s",
        ) from exc

    if out_thread:
        out_thread.join(timeout=1.0)
    if err_thread:
        err_thread.join(timeout=1.0)

    stdout_raw = stdout_buf[0] if stdout_buf else b""
    stderr_raw = stderr_buf[0] if stderr_buf else b""

    # Redact output if text
    if text:
        stdout_clean = redact_text(
            stdout_raw.decode("utf-8", errors="replace"), secrets
        )
        stderr_clean = redact_text(
            stderr_raw.decode("utf-8", errors="replace"), secrets
        )
        completed = subprocess.CompletedProcess(
            args=[redact_text(arg, secrets) for arg in cmd_list],
            returncode=returncode,
            stdout=stdout_clean,
            stderr=stderr_clean,
        )
    else:
        completed = subprocess.CompletedProcess(
            args=[redact_text(arg, secrets) for arg in cmd_list],
            returncode=returncode,
            stdout=stdout_raw,
            stderr=stderr_raw,
        )

    if check and completed.returncode != 0:
        safe_cmd = [redact_text(arg, secrets) for arg in cmd_list]
        raise SafeSubprocessError(
            cmd=safe_cmd,
            returncode=completed.returncode,
            stdout=completed.stdout[:max_output_length]
            if isinstance(completed.stdout, str)
            else "",
            stderr=completed.stderr[:max_output_length]
            if isinstance(completed.stderr, str)
            else "",
            timed_out=False,
        )

    return completed
