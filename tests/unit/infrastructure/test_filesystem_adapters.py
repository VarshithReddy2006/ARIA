"""Unit tests for Filesystem & Workspace Infrastructure Adapters."""

from pathlib import Path

import pytest
from ria.domain.common.value_objects import UUIDv4
from ria.domain.sync.value_objects import RepositoryIdentity
from ria.infrastructure.exceptions import FilesystemError, WorkspaceError
from ria.infrastructure.filesystem import OSFilesystemAdapter, WorkspaceManager


def test_os_filesystem_adapter_read_and_walk(tmp_path: Path) -> None:
    fs = OSFilesystemAdapter()

    sub_dir = tmp_path / "src"
    sub_dir.mkdir()
    f1 = sub_dir / "main.py"
    f1.write_bytes(b"print('hello')")

    f2 = sub_dir / "ignored.pyc"
    f2.write_bytes(b"binary")

    assert fs.exists(f1)
    assert fs.read_bytes(f1) == b"print('hello')"
    assert fs.get_size(f1) == 14

    discovered = fs.walk_directory(tmp_path, ignore_patterns=["*.pyc"])
    assert len(discovered) == 1
    assert discovered[0].name == "main.py"


def test_os_filesystem_adapter_error_handling(tmp_path: Path) -> None:
    fs = OSFilesystemAdapter()
    missing = tmp_path / "non_existent.py"
    with pytest.raises(FilesystemError):
        fs.read_bytes(missing)


def test_workspace_manager(tmp_path: Path) -> None:
    wm = WorkspaceManager(base_dir=tmp_path)
    identity = RepositoryIdentity(
        repo_id=UUIDv4.generate(),
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )

    path = wm.create_workspace(identity)
    assert path.exists()
    assert path.is_dir()

    ephemeral = wm.create_ephemeral_workspace(identity, suffix="test")
    assert ephemeral.exists()

    assert wm.delete_workspace(identity)
    assert not path.exists()


def test_workspace_manager_path_traversal_prevention(tmp_path: Path) -> None:
    wm = WorkspaceManager(base_dir=tmp_path)
    # Inject bad path attempting traversal
    bad_path = tmp_path.parent / "outside"
    with pytest.raises(WorkspaceError, match="Path traversal"):
        wm._validate_workspace_path(bad_path)
