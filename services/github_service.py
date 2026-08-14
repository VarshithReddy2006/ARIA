"""GitHub Service module.

Interfaces with the GitHub API to fetch repository structures, file contents,
issue lists, and pull request information, or clones repositories locally.
"""

import os
import re
import shutil
import stat
import urllib.parse
import logging
from typing import Dict, List, Any, Optional
import requests

from services.storage_paths import get_cloned_repos_dir
from utils.subprocess_runner import (
    run_safe_command,
    SafeSubprocessError,
    SHORT_GIT_TIMEOUT,
    INSPECTION_TIMEOUT,
    CLONE_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Client-safe failure messages. These must never disclose whether a repository
# exists, whether credentials are configured, or whether credentials are valid,
# and must never carry git stderr, git commands, or exception text.
ACCESS_DENIED_MESSAGE = "Repository not found or access denied."
NETWORK_FAILURE_MESSAGE = (
    "Network failure: unable to reach the repository host. Please try again."
)
GIT_FAILURE_MESSAGE = "Connection failure: unable to complete the repository operation."

# Internal diagnostic categories. Every category is logged distinctly for
# operators; several intentionally collapse to one public message.
_CATEGORY_INVALID_CREDENTIALS = "invalid_credentials"
_CATEGORY_PERMISSION_DENIED = "permission_denied"
_CATEGORY_NOT_FOUND = "not_found"
_CATEGORY_NETWORK = "network"
_CATEGORY_GIT_FAILURE = "git_failure"
_CATEGORY_UNEXPECTED = "unexpected"

_NON_DISCLOSING_CATEGORIES = frozenset(
    {
        _CATEGORY_INVALID_CREDENTIALS,
        _CATEGORY_PERMISSION_DENIED,
        _CATEGORY_NOT_FOUND,
    }
)


class InvalidGitHubRepoURLError(ValueError):
    """Raised when the provided repo URL/identifier is not a supported GitHub format."""


class RepositoryNotFoundError(RuntimeError):
    """Raised when the target repository cannot be accessed (404-like git failure)."""


class GitOperationError(RuntimeError):
    """Raised when a git operation fails for network or execution reasons."""


class BranchNotFoundError(ValueError):
    """Raised when the requested branch/ref does not exist in the repository."""


def classify_git_failure(
    stderr: str, returncode: int = 0, timed_out: bool = False
) -> str:
    """Classify a git failure into an internal diagnostic category.

    Args:
        stderr: Redacted git stderr output.
        returncode: Process exit code.
        timed_out: Whether the command exceeded its timeout.

    Returns:
        One of the internal ``_CATEGORY_*`` values.
    """
    if timed_out:
        return _CATEGORY_NETWORK

    text = (stderr or "").lower()

    # Local execution problems must not be mistaken for repository access
    # results, because their stderr also contains "not found".
    if any(
        kw in text
        for kw in (
            "executable not found",
            "no such file or directory",
            "cannot run program",
        )
    ):
        return _CATEGORY_GIT_FAILURE

    if any(
        kw in text
        for kw in (
            "could not resolve host",
            "temporary failure",
            "network is unreachable",
            "connection refused",
            "connection timed out",
            "timed out",
            "operation timed out",
            "failed to connect",
        )
    ):
        return _CATEGORY_NETWORK

    if any(
        kw in text
        for kw in (
            "401",
            "invalid username or password",
            "bad credentials",
            "authentication failed",
            "could not read username",
            "terminal prompts disabled",
        )
    ):
        return _CATEGORY_INVALID_CREDENTIALS

    if any(
        kw in text
        for kw in (
            "403",
            "forbidden",
            "permission denied",
            "write access",
            "authorization",
        )
    ):
        return _CATEGORY_PERMISSION_DENIED

    if any(
        kw in text
        for kw in ("404", "not found", "repository not found", "fatal: repository")
    ):
        return _CATEGORY_NOT_FOUND

    if returncode != 0:
        return _CATEGORY_GIT_FAILURE

    return _CATEGORY_UNEXPECTED


class GitHubConfig:
    token: Optional[str] = None

    @classmethod
    def load_token(cls) -> Optional[str]:
        if cls.token is None:
            from core.config import settings

            cls.token = settings.github_token
        return cls.token


class GitHubService:
    """Wrapper class containing helpers to query GitHub repositories or clone them locally."""

    _APPROVED_HOST = "github.com"
    _MAX_SOURCE_FILE_SIZE_BYTES = 2 * 1024 * 1024
    _REPOSITORY_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

    def _raise_safe_git_error(
        self,
        category: str,
        *,
        repo_fullName: str,
        cmd: Optional[List[str]] = None,
        stderr: str = "",
        returncode: int = 0,
        exc: Optional[BaseException] = None,
    ) -> None:
        """Log full git diagnostics for operators, then raise a client-safe error.

        Diagnostics (category, git command, repository, exit code, stderr and the
        underlying exception) are written to the server log only. The raised
        exception message is generic and never reveals repository existence or
        credential state.

        Raises:
            RepositoryNotFoundError: For credential, permission and not-found cases.
            GitOperationError: For network, git-execution and unexpected cases.
        """
        logger.error(
            "GitHub operation failed | category=%s repository=%s exit_code=%s "
            "credentials_configured=%s command=%s stderr=%s",
            category,
            repo_fullName,
            returncode,
            bool(self.token),
            " ".join(cmd) if cmd else "n/a",
            (stderr or "").strip() or "n/a",
            exc_info=exc if exc is not None else False,
        )

        if category in _NON_DISCLOSING_CATEGORIES:
            raise RepositoryNotFoundError(ACCESS_DENIED_MESSAGE)
        if category == _CATEGORY_NETWORK:
            raise GitOperationError(NETWORK_FAILURE_MESSAGE)
        raise GitOperationError(GIT_FAILURE_MESSAGE)

    def _run_git(
        self,
        cmd: List[str],
        *,
        timeout: float,
        repo_fullName: str,
        env: Optional[Dict[str, str]] = None,
        secrets: Optional[List[str]] = None,
        cwd: Optional[str] = None,
    ) -> Any:
        """Run a git command, converting execution failures into client-safe errors."""
        try:
            return run_safe_command(
                cmd, timeout=timeout, env=env, secrets=secrets or [], cwd=cwd
            )
        except SafeSubprocessError as sub_exc:
            self._raise_safe_git_error(
                classify_git_failure(
                    sub_exc.stderr, sub_exc.returncode, sub_exc.timed_out
                ),
                repo_fullName=repo_fullName,
                cmd=cmd,
                stderr=sub_exc.stderr,
                returncode=sub_exc.returncode,
                exc=sub_exc,
            )

    def __init__(self, token: Optional[str] = None) -> None:
        """Initializes the GitHub client with an optional authentication token.

        Args:
            token: GitHub Personal Access Token (PAT).
        """
        self.token = token or GitHubConfig.load_token()
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.session.headers.update({"Accept": "application/vnd.github+json"})

        # Verify request headers
        logger.info(
            "GitHub Authorization header present: %s",
            "Authorization" in self.session.headers,
        )

    def parse_repo_url(self, repo_url: str) -> Dict[str, str]:
        """Parse a supported GitHub URL or ``owner/repo`` identifier safely."""
        raw_url = repo_url.strip()
        if not raw_url:
            raise ValueError("Invalid GitHub repository URL.")

        owner: Optional[str] = None
        repo: Optional[str] = None
        parsed = urllib.parse.urlparse(raw_url)

        if parsed.scheme or parsed.netloc:
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname != self._APPROVED_HOST
                or parsed.port is not None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Invalid GitHub repository URL.")
            path_parts = [part for part in parsed.path.split("/") if part]
        else:
            path_parts = [part for part in raw_url.split("/") if part]
            if len(path_parts) == 3 and path_parts[0] == self._APPROVED_HOST:
                path_parts = path_parts[1:]

        if len(path_parts) == 2:
            owner, repo = path_parts
            if repo.endswith(".git"):
                repo = repo[:-4]

        if (
            not owner
            or not repo
            or not self._REPOSITORY_PART.fullmatch(owner)
            or not self._REPOSITORY_PART.fullmatch(repo)
        ):
            raise ValueError("Invalid GitHub repository URL.")

        return {"owner": owner, "repo": repo}

    def get_local_repo_path(self, repo_fullName: str) -> str:
        """Returns the local path where a repository is or should be cloned.

        Args:
            repo_fullName: GitHub owner/repo identifier.

        Returns:
            The local directory path.
        """
        # Store clones OUTSIDE the project tree so uvicorn --reload (WatchFiles)
        # does not treat clone activity as source-code changes. Configurable via
        # CLONED_REPOS_PATH; defaults to ~/.repo_intelligence/cloned_repos.
        base_dir = str(get_cloned_repos_dir())
        safe_name = repo_fullName.replace("/", "_").replace("\\", "_")
        return os.path.abspath(os.path.join(base_dir, safe_name))

    def clone_repository(self, repo_url: str, branch: Optional[str] = None) -> str:
        """Clones a GitHub repository to a local directory using Git CLI with fallback reliability.

        Args:
            repo_url: GitHub repository URL or owner/repo identifier.
            branch: Optional branch/ref name to clone. If provided, existence is validated.

        Returns:
            The local path to the cloned repository.
        """

        try:
            parsed = self.parse_repo_url(repo_url)
        except ValueError as e:
            raise InvalidGitHubRepoURLError(str(e))

        repo_fullName = f"{parsed['owner']}/{parsed['repo']}"
        dest_dir = self.get_local_repo_path(repo_fullName)

        # Always use the canonical approved host. Credentials are never attached
        # to a caller-provided remote URL.
        public_url = f"https://{self._APPROVED_HOST}/{repo_fullName}.git"

        # Prepare authorization environment & secret redaction list
        extra_env: Dict[str, str] = {}
        secrets_list: List[str] = []
        if self.token:
            import base64

            auth_str = base64.b64encode(
                f"x-access-token:{self.token}".encode("utf-8")
            ).decode("utf-8")
            extra_env = {
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth_str}",
            }
            secrets_list = [self.token, auth_str]

        # 2. Check if repository is publicly accessible (anonymous check)
        is_public = False
        try:
            cmd_check = ["git", "ls-remote", public_url, "HEAD"]
            res = run_safe_command(
                cmd_check, timeout=SHORT_GIT_TIMEOUT, secrets=secrets_list
            )
            if res.returncode == 0:
                is_public = True
        except Exception:
            pass

        # 3. Determine actual URL to use
        clone_url = public_url
        if is_public:
            logger.info("Cloning public repository anonymously: %s", repo_fullName)
        elif self.token:
            logger.info("Cloning private repository using PAT: %s", repo_fullName)
        else:
            logger.info(
                "Cloning repository anonymously (no token available): %s", repo_fullName
            )

        # 4. Perform ls-remote connection diagnostics
        cmd_check = ["git", "ls-remote", clone_url, "HEAD"]
        res = self._run_git(
            cmd_check,
            timeout=SHORT_GIT_TIMEOUT,
            repo_fullName=repo_fullName,
            env=extra_env,
            secrets=secrets_list,
        )
        if res.returncode != 0:
            self._raise_safe_git_error(
                classify_git_failure(res.stderr, res.returncode),
                repo_fullName=repo_fullName,
                cmd=cmd_check,
                stderr=res.stderr,
                returncode=res.returncode,
            )

        # 5. Resolve Branch name (and auto-discover if requested branch is default 'main' but not present)
        actual_branch = branch
        if branch:
            # Check if requested branch exists
            cmd_check = ["git", "ls-remote", "--heads", clone_url, branch]
            res_check = self._run_git(
                cmd_check,
                timeout=INSPECTION_TIMEOUT,
                repo_fullName=repo_fullName,
                env=extra_env,
                secrets=secrets_list,
            )
            branch_exists = res_check.returncode == 0 and bool(res_check.stdout.strip())

            if not branch_exists:
                if branch == "main":
                    # Try to auto-discover default branch
                    try:
                        cmd_sym = ["git", "ls-remote", "--symref", clone_url, "HEAD"]
                        res_sym = self._run_git(
                            cmd_sym,
                            timeout=INSPECTION_TIMEOUT,
                            repo_fullName=repo_fullName,
                            env=extra_env,
                            secrets=secrets_list,
                        )
                        discovered = None
                        if res_sym.returncode == 0:
                            for line in res_sym.stdout.splitlines():
                                if line.startswith("ref:"):
                                    parts = line.split()
                                    if len(parts) >= 2 and parts[1].startswith(
                                        "refs/heads/"
                                    ):
                                        discovered = parts[1].replace("refs/heads/", "")
                                        break
                        if discovered:
                            actual_branch = discovered
                            logger.info(
                                f"Branch 'main' not found. Auto-discovered default branch: '{actual_branch}'"
                            )
                        else:
                            raise BranchNotFoundError(
                                "Branch 'main' not found, and failed to auto-discover default branch."
                            )
                    except Exception as e:
                        if isinstance(
                            e,
                            (
                                BranchNotFoundError,
                                RepositoryNotFoundError,
                                GitOperationError,
                            ),
                        ):
                            raise e
                        raise BranchNotFoundError(
                            f"Branch 'main' not found for repository {repo_fullName}."
                        )
                else:
                    raise BranchNotFoundError(
                        f"Branch '{branch}' does not exist for repository {repo_fullName}."
                    )

        # 6. Check if target directory already exists with a valid git repository
        if os.path.exists(dest_dir) and os.path.exists(os.path.join(dest_dir, ".git")):
            target_branch = actual_branch or "main"
            logger.info(
                f"Existing repository clone found at {dest_dir}. Updating via git fetch (branch={target_branch})..."
            )
            try:
                cmd_fetch = ["git", "fetch", "--depth", "1", clone_url, target_branch]
                res_fetch = self._run_git(
                    cmd_fetch,
                    timeout=CLONE_TIMEOUT,
                    repo_fullName=repo_fullName,
                    env=extra_env,
                    secrets=secrets_list,
                    cwd=dest_dir,
                )
                if res_fetch.returncode == 0:
                    cmd_reset = ["git", "reset", "--hard", "FETCH_HEAD"]
                    res_reset = self._run_git(
                        cmd_reset,
                        timeout=SHORT_GIT_TIMEOUT,
                        repo_fullName=repo_fullName,
                        env=extra_env,
                        secrets=secrets_list,
                        cwd=dest_dir,
                    )
                    if res_reset.returncode == 0:
                        logger.info(f"Successfully updated repository at {dest_dir}")
                        return dest_dir
            except Exception as exc:
                logger.warning(
                    f"Failed to update existing clone at {dest_dir}: {exc}. Cleaning up for full clone..."
                )

        # 7. Clear target directory if it exists and needs clean re-clone
        if os.path.exists(dest_dir):
            import stat

            def _remove_readonly(func, path, exc_info):
                os.chmod(path, stat.S_IWRITE)
                func(path)

            try:
                shutil.rmtree(dest_dir, onerror=_remove_readonly)
            except Exception as e:
                logger.warning(
                    f"Failed to completely remove existing directory {dest_dir}: {e}."
                )

        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)

        # 8. Perform Clone
        logger.info(
            f"Cloning repository {repo_fullName} to {dest_dir} (branch={actual_branch})..."
        )
        cmd = ["git", "clone", "--depth", "1", "--single-branch"]
        if actual_branch:
            cmd.extend(["--branch", actual_branch])
        cmd.extend([clone_url, dest_dir])

        result = self._run_git(
            cmd,
            timeout=CLONE_TIMEOUT,
            repo_fullName=repo_fullName,
            env=extra_env,
            secrets=secrets_list,
        )
        if result.returncode != 0:
            self._raise_safe_git_error(
                classify_git_failure(result.stderr, result.returncode),
                repo_fullName=repo_fullName,
                cmd=cmd,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        return dest_dir

    def _safe_source_file(self, file_path: str, repository_path: str) -> bool:
        """Return whether a file can be read without escaping the checkout."""
        try:
            if os.path.islink(file_path):
                return False
            file_stat = os.lstat(file_path)
            if not stat.S_ISREG(file_stat.st_mode):
                return False
            if file_stat.st_size > self._MAX_SOURCE_FILE_SIZE_BYTES:
                return False
            resolved_repository = os.path.realpath(repository_path)
            resolved_file = os.path.realpath(file_path)
            return (
                os.path.commonpath([resolved_repository, resolved_file])
                == resolved_repository
            )
        except (OSError, ValueError):
            return False

    def extract_source_files(self, local_path: str) -> List[Dict[str, Any]]:
        """Walks the cloned repository and extracts safe, bounded text files."""
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
        extracted_files = []

        for root, dirs, files in os.walk(local_path):
            dirs[:] = [
                d
                for d in dirs
                if d not in ignored_names and not os.path.islink(os.path.join(root, d))
            ]

            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, local_path)

                parts = rel_path.split(os.sep)
                if any(part in ignored_names for part in parts):
                    continue

                ext = os.path.splitext(file)[1].lower()
                if ext in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".ico",
                    ".pdf",
                    ".zip",
                    ".tar",
                    ".gz",
                    ".mp3",
                    ".mp4",
                    ".woff",
                    ".woff2",
                    ".ttf",
                    ".eot",
                    ".svg",
                    ".pyc",
                    ".db",
                    ".sqlite",
                    ".exe",
                    ".bin",
                    ".dll",
                    ".so",
                    ".dylib",
                    ".pkl",
                    ".h5",
                }:
                    continue

                if not self._safe_source_file(file_path, local_path):
                    logger.debug(
                        "Skipping unsafe or oversized source file: %s", rel_path
                    )
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    extracted_files.append(
                        {"path": rel_path.replace(os.sep, "/"), "content": content}
                    )
                except OSError as exc:
                    logger.debug(
                        "Skipping file %s due to read error: %s", rel_path, exc
                    )

        return extracted_files

    def fetch_repository_files(
        self, repo_fullName: str, branch: str = "main"
    ) -> List[Dict[str, Any]]:
        """Queries the local repository clone or fallback API to get all file metadata recursively.

        Args:
            repo_fullName: GitHub owner/repo identifier (e.g., "google/guava").
            branch: Target branch name.

        Returns:
            A list of dictionary records containing file paths, types, sizes, and URLs.
        """
        dest_dir = self.get_local_repo_path(repo_fullName)

        # If not cloned, clone it
        if not os.path.exists(dest_dir):
            repo_url = f"https://github.com/{repo_fullName}.git"
            try:
                self.clone_repository(repo_url)
            except Exception as e:
                logger.error(f"Clone failed inside fetch_repository_files: {e}")
                raise

        files_meta = []
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

        for root, dirs, files in os.walk(dest_dir):
            dirs[:] = [
                d
                for d in dirs
                if d not in ignored_names and not os.path.islink(os.path.join(root, d))
            ]
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, dest_dir).replace(os.sep, "/")
                if any(part in ignored_names for part in rel_path.split("/")):
                    continue
                if not self._safe_source_file(file_path, dest_dir):
                    continue
                size = os.path.getsize(file_path)
                files_meta.append(
                    {
                        "path": rel_path,
                        "type": "blob",
                        "size": size,
                        "url": f"https://github.com/{repo_fullName}/blob/{branch}/{rel_path}",
                    }
                )
        return files_meta

    def fetch_file_content(
        self, repo_fullName: str, file_path: str, ref: str = "main"
    ) -> str:
        """Downloads/reads the raw content of a specific file from a GitHub repository clone.

        Args:
            repo_fullName: GitHub owner/repo identifier.
            file_path: Relative path to the file.
            ref: Git commit or branch ref.

        Returns:
            The raw text content of the file.
        """
        dest_dir = self.get_local_repo_path(repo_fullName)
        local_file = os.path.join(dest_dir, file_path.replace("/", os.sep))

        if os.path.exists(local_file):
            try:
                with open(local_file, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                raise IOError(f"Error reading file {file_path} from local storage: {e}")

        # If not found locally, try to fetch via GitHub API
        if not self.token:
            raise RuntimeError("GitHub credentials are not configured.")
        url = f"https://api.github.com/repos/{repo_fullName}/contents/{file_path}?ref={ref}"
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            if "content" in data and data.get("encoding") == "base64":
                import base64

                return base64.b64decode(data["content"]).decode(
                    "utf-8", errors="ignore"
                )
            elif "download_url" in data:
                raw_resp = requests.get(data["download_url"])
                raw_resp.raise_for_status()
                return raw_resp.text
        except Exception as e:
            logger.error(f"Failed to fetch remote file content for {file_path}: {e}")

        raise FileNotFoundError(
            f"File {file_path} not found locally or remotely for repository {repo_fullName}."
        )

    def fetch_issues(
        self, repo_fullName: str, state: str = "open"
    ) -> List[Dict[str, Any]]:
        """Queries GitHub Issues API to fetch issues for mapping analysis.

        Args:
            repo_fullName: GitHub owner/repo identifier.
            state: Status of issues to retrieve ("open", "closed", "all").

        Returns:
            A list of dictionary records containing issue numbers, titles, bodies, and URLs.
        """
        if not self.token:
            raise RuntimeError("GitHub credentials are not configured.")
        url = f"https://api.github.com/repos/{repo_fullName}/issues"
        params = {"state": state, "per_page": 100}

        try:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            issues = resp.json()

            result = []
            for issue in issues:
                # GitHub issues endpoint also returns pull requests, filter them out
                if "pull_request" in issue:
                    continue
                result.append(
                    {
                        "number": issue.get("number"),
                        "title": issue.get("title"),
                        "body": issue.get("body", ""),
                        "url": issue.get("html_url"),
                        "state": issue.get("state"),
                    }
                )
            return result
        except Exception as e:
            logger.error(f"Failed to fetch issues for {repo_fullName}: {e}")
            # Fallback to empty list or raise depending on preferences
            return []

    def fetch_pull_request_metadata(
        self, owner: str, repo: str, pr_number: int
    ) -> Dict[str, Any]:
        """Fetch PR metadata from the GitHub API.

        Args:
            owner: Owner of the repository.
            repo: Name of the repository.
            pr_number: Pull request number.

        Returns:
            Dict containing title, state, html_url, additions, deletions, etc.
        """
        if not self.token:
            raise RuntimeError("GitHub credentials are not configured.")
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            return {
                "title": data.get("title", ""),
                "state": data.get("state", "open"),
                "html_url": data.get("html_url", ""),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
                "head_sha": data.get("head", {}).get("sha", ""),
            }
        except Exception as e:
            logger.error(
                f"Failed to fetch PR metadata for {owner}/{repo}/pulls/{pr_number}: {e}"
            )
            raise RuntimeError(f"Failed to fetch PR metadata: {e}")

    def fetch_pull_request_files(
        self, owner: str, repo: str, pr_number: int
    ) -> List[Dict[str, Any]]:
        """Fetch files changed in a PR from the GitHub API (handles pagination).

        Args:
            owner: Owner of the repository.
            repo: Name of the repository.
            pr_number: Pull request number.

        Returns:
            List of dict records for each changed file.
        """
        if not self.token:
            raise RuntimeError("GitHub credentials are not configured.")
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        result = []
        page = 1
        per_page = 100

        while True:
            try:
                resp = self.session.get(
                    url, params={"page": page, "per_page": per_page}
                )
                resp.raise_for_status()
                files = resp.json()
                if not files:
                    break
                for f in files:
                    result.append(
                        {
                            "filename": f.get("filename", ""),
                            "status": f.get("status", ""),
                            "additions": f.get("additions", 0),
                            "deletions": f.get("deletions", 0),
                            "changes": f.get("changes", 0),
                        }
                    )
                if len(files) < per_page:
                    break
                page += 1
            except Exception as e:
                logger.error(
                    f"Failed to fetch PR files for {owner}/{repo}/pulls/{pr_number} page {page}: {e}"
                )
                raise RuntimeError(f"Failed to fetch PR files: {e}")

        return result

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Fetch rate limit information from the GitHub API.

        Returns:
            Dict containing remaining rate limit, reset time, etc.
        """
        if not self.token:
            raise RuntimeError("GitHub credentials are not configured.")
        url = "https://api.github.com/rate_limit"
        try:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("resources", {}).get("core", {})
            return {
                "limit": rate.get("limit", 0),
                "remaining": rate.get("remaining", 0),
                "reset": rate.get("reset", 0),
            }
        except Exception as e:
            logger.error(f"Failed to fetch rate limit info: {e}")
            return {
                "limit": 0,
                "remaining": 0,
                "reset": 0,
            }
