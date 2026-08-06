"""Unit tests for Settings, Container, and Git Adapters."""

from pathlib import Path

from ria.config import Container, Settings
from ria.infrastructure.git import SubprocessGitAdapter


def test_settings_and_container(tmp_path: Path) -> None:
    settings = Settings.create_testing(tmp_path)
    container = Container.create(settings)

    assert container.settings.environment == "testing"
    assert container.clock is not None
    assert container.filesystem is not None
    assert container.workspace_manager is not None
    assert container.repository_registry is not None
    assert container.repository_lock is not None
    assert container.git_client is not None


def test_subprocess_git_adapter_local_repo(tmp_path: Path) -> None:
    """Integration test of SubprocessGitAdapter against a local git repository."""
    import subprocess

    # Create dummy local git repo
    repo_dir = tmp_path / "origin_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True
    )

    dummy_file = repo_dir / "README.md"
    dummy_file.write_text("hello git")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True)

    git_adapter = SubprocessGitAdapter(timeout_seconds=10.0)

    # 1. Get current commit
    commit = git_adapter.get_current_commit(repo_dir)
    assert len(commit.sha) == 40

    # 2. Get metadata
    meta = git_adapter.get_metadata(repo_dir, default_branch="main")
    assert meta.file_count == 1
    assert meta.total_bytes > 0

    # 3. Clone to target dir
    clone_dir = tmp_path / "cloned_repo"
    cloned_commit = git_adapter.clone(str(repo_dir), clone_dir)
    assert cloned_commit.sha == commit.sha
