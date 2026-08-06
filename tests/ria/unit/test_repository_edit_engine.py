"""Unit tests for RepositoryEditEngineService (Phase 3)."""

from __future__ import annotations


from ria.application.repository_edit_engine import RepositoryEditEngineService
from ria.domain.models.repository_edit_models import RepositoryEdit


def test_repository_edit_engine_service() -> None:
    svc = RepositoryEditEngineService()
    edit1 = RepositoryEdit(
        file_path="main.py", edit_type="create", new_content="def main(): pass"
    )
    edit2 = RepositoryEdit(
        file_path="utils.py", edit_type="modify", new_content="def foo(): return 1"
    )

    patch = svc.apply_edits((edit1, edit2), dry_run=True)

    assert patch.statistics.files_changed == 2
    assert patch.statistics.insertions >= 2
    assert len(patch.files) == 2
