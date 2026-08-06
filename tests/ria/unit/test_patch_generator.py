"""Unit tests for PatchGeneratorService (Phase 4)."""

from __future__ import annotations


from ria.application.patch_generator import PatchGeneratorService
from ria.domain.models.repository_edit_models import RepositoryEdit


def test_patch_generator_service() -> None:
    svc = PatchGeneratorService()
    edit = RepositoryEdit(
        file_path="app.py", edit_type="modify", new_content="print('hello')"
    )

    patch = svc.generate_patch((edit,))
    assert patch.statistics.files_changed == 1
    assert patch.statistics.insertions == 1
    assert patch.files[0].file_path == "app.py"
