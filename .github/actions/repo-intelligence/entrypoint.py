"""GitHub Action entrypoint for ARIA.

Drives one PR through three steps:
1. Call the hosted backend's `/api/v1/pr/analyze` to get a `PRAnalysisResult`.
2. Upsert a single sticky comment on the PR (find-by-marker, PATCH or POST).
3. Create a Check Run summarising the result.

Inputs come from environment variables set by `action.yml`. No analysis logic
lives here — the backend owns the existing PRIntelligenceService pipeline.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx

# Make the repo's `models/` and `services/` importable so we can reuse the
# shared renderer and the existing Pydantic model without copy-pasting.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from models.pr_intelligence import PRAnalysisResult  # noqa: E402
from services.github_review_renderer import (  # noqa: E402
    STICKY_MARKER,
    check_conclusion_for,
    render_check_summary,
    render_pr_review,
)

logging.basicConfig(
    format="[repo-intel] %(levelname)s %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger("repo-intelligence-action")


# -- env / output helpers --------------------------------------------------


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        logger.error("Required environment variable missing: %s", name)
        sys.exit(2)
    return val


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _emit_output(key: str, value: str) -> None:
    """Write an Action output via `$GITHUB_OUTPUT` (multiline-safe)."""
    out_path = os.environ.get("GITHUB_OUTPUT")
    if not out_path:
        return
    with open(out_path, "a", encoding="utf-8") as fh:
        if "\n" in value:
            delim = f"REPO_INTEL_{int(time.time() * 1000)}"
            fh.write(f"{key}<<{delim}\n{value}\n{delim}\n")
        else:
            fh.write(f"{key}={value}\n")


# -- analysis client -------------------------------------------------------


def fetch_pr_analysis(
    api_url: str,
    owner: str,
    repo: str,
    pr_number: int,
    api_token: Optional[str] = None,
    *,
    client: Optional[httpx.Client] = None,
) -> PRAnalysisResult:
    """POST to `{api_url}/api/v1/pr/analyze` and parse the result."""
    headers = {"Accept": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    endpoint = f"{api_url.rstrip('/')}/api/v1/pr/analyze"
    payload = {"owner": owner, "repo": repo, "pr_number": pr_number}

    if client is not None:
        resp = client.post(endpoint, headers=headers, json=payload, timeout=300.0)
    else:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=300.0)
    resp.raise_for_status()
    return PRAnalysisResult.model_validate(resp.json())


# -- github helpers --------------------------------------------------------


class GitHub:
    """Minimal GitHub REST helper for the Action's three calls."""

    def __init__(
        self,
        token: str,
        api_url: str = "https://api.github.com",
        *,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=api_url,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def find_sticky_comment(
        self, owner: str, repo: str, pr_number: int
    ) -> Optional[dict[str, Any]]:
        """Walk issue comments looking for STICKY_MARKER; returns first match."""
        page = 1
        while True:
            r = self._client.get(
                f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            r.raise_for_status()
            comments = r.json()
            for c in comments:
                if STICKY_MARKER in (c.get("body") or ""):
                    return c
            if len(comments) < 100:
                return None
            page += 1

    def upsert_sticky_comment(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> dict[str, Any]:
        existing = self.find_sticky_comment(owner, repo, pr_number)
        if existing:
            r = self._client.patch(
                f"/repos/{owner}/{repo}/issues/comments/{existing['id']}",
                json={"body": body},
            )
        else:
            r = self._client.post(
                f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
                json={"body": body},
            )
        r.raise_for_status()
        return r.json()

    def create_check_run(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        name: str,
        conclusion: str,
        title: str,
        summary: str,
    ) -> dict[str, Any]:
        r = self._client.post(
            f"/repos/{owner}/{repo}/check-runs",
            json={
                "name": name,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": conclusion,
                "output": {"title": title, "summary": summary},
            },
        )
        r.raise_for_status()
        return r.json()


# -- main ------------------------------------------------------------------


def main() -> int:
    github_token = _required("INPUT_GITHUB_TOKEN")
    api_url = _required("INPUT_API_URL")
    api_token = _optional("INPUT_API_TOKEN") or None
    owner = _required("INPUT_OWNER")
    repo = _required("INPUT_REPO")
    pr_number = int(_required("INPUT_PR_NUMBER"))
    head_sha = _required("INPUT_HEAD_SHA")
    check_name = _optional("INPUT_CHECK_NAME", "Repository Intelligence")
    github_api_url = _optional("GITHUB_API_URL", "https://api.github.com")

    logger.info("Analyzing %s/%s PR #%d at %s", owner, repo, pr_number, head_sha[:7])
    started = time.perf_counter()
    try:
        result = fetch_pr_analysis(api_url, owner, repo, pr_number, api_token)
    except httpx.HTTPError as exc:
        logger.error("PR analysis failed: %s", exc)
        return 1
    elapsed = time.perf_counter() - started

    gh = GitHub(github_token, github_api_url)
    try:
        comment = gh.upsert_sticky_comment(
            owner, repo, pr_number, render_pr_review(result)
        )
        comment_url = comment.get("html_url") or ""
        logger.info("Sticky comment posted: %s", comment_url)

        gh.create_check_run(
            owner,
            repo,
            head_sha,
            name=check_name,
            conclusion=check_conclusion_for(result.risk_level),
            title=f"Risk {result.risk_level} ({result.risk_score}/100)",
            summary=render_check_summary(result, elapsed, comment_url or None),
        )
        logger.info("Check Run created (%.1fs total)", elapsed)
    except httpx.HTTPError as exc:
        logger.error("GitHub API call failed: %s", exc)
        return 1

    _emit_output("risk-score", str(result.risk_score))
    _emit_output("risk-level", result.risk_level)
    _emit_output("comment-url", comment_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
