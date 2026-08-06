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
from typing import Dict, Optional, Sequence, Union

logger = logging.getLogger(__name__)

# Standard timeout categories (in seconds)
SHORT_GIT_TIMEOUT = 15.0
INSPECTION_TIMEOUT = 30.0
HISTORY_ANALYSIS_TIMEOUT = 120.0
CLONE_TIMEOUT = 300.0
DEFAULT_TIMEOUT = 30.0

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
) -> subprocess.CompletedProcess:
    """Executes a subprocess safely with mandatory timeout, non-shell execution, and secret redaction.

    Args:
        cmd: Command and arguments list. Must be a sequence of strings.
        cwd: Directory in which to execute the command.
        timeout: Execution timeout in seconds.
        env: Additional environment variables to set.
        secrets: List of sensitive strings to redact from logs, errors, and output.
        check: If True, raises SafeSubprocessError on non-zero exit code.
        capture_output: If True, capture stdout and stderr.
        text: If True, decode output as utf-8 text.
        max_output_length: Maximum length of stdout/stderr kept in exceptions.

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

    try:
        completed = subprocess.run(
            cmd_list,
            cwd=cwd,
            timeout=timeout,
            shell=False,  # Strictly non-shell execution
            capture_output=capture_output,
            text=text,
            env=merged_env,
            check=False,  # We handle return code manually for safe secret redaction
        )
    except subprocess.TimeoutExpired as exc:
        stdout_str = (
            redact_text(exc.stdout or "", secrets) if text and exc.stdout else ""
        )
        stderr_str = (
            redact_text(exc.stderr or "", secrets) if text and exc.stderr else ""
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

    # Redact output if text
    if text:
        stdout_clean = redact_text(completed.stdout or "", secrets)
        stderr_clean = redact_text(completed.stderr or "", secrets)
        completed = subprocess.CompletedProcess(
            args=[redact_text(arg, secrets) for arg in cmd_list],
            returncode=completed.returncode,
            stdout=stdout_clean,
            stderr=stderr_clean,
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
