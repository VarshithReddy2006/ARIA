"""Resolve writable storage locations outside the project tree.

Cloned repositories MUST live outside the project root, otherwise
`uvicorn --reload` (WatchFiles) treats every cloned file as a source-code
change and kills the in-flight analysis request.

Resolution order:
1. `CLONED_REPOS_PATH` env var (recommended, e.g. C:/repo_intelligence_storage/cloned_repos)
2. `~/.repo_intelligence/cloned_repos` (cross-platform fallback)
"""

from __future__ import annotations

from pathlib import Path


def get_cloned_repos_dir() -> Path:
    """Return the base directory for cloned repositories, creating it if needed.

    Never returns a path inside the project tree — keeps WatchFiles quiet.
    """
    from core.config import settings

    raw = settings.cloned_repos_path.strip()
    base = (
        Path(raw).expanduser()
        if raw
        else Path.home() / ".repo_intelligence" / "cloned_repos"
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


if __name__ == "__main__":
    # ponytail: minimal self-check — proves the dir exists and lives outside cwd.
    p = get_cloned_repos_dir()
    assert p.exists() and p.is_dir(), f"clone dir not created: {p}"
    assert Path.cwd() not in p.parents and p != Path.cwd(), (
        f"clone dir inside project: {p}"
    )
    print(f"OK cloned_repos_dir={p}")
