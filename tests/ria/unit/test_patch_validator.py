"""Unit tests for PatchValidatorService (Phase 5)."""

from __future__ import annotations


from ria.application.patch_validator import PatchValidatorService
from ria.domain.models.patch_models import ExecutionPatch, PatchChunk, PatchFile


def test_patch_validator_service() -> None:
    svc = PatchValidatorService()
    chunk = PatchChunk(
        start_line=1, end_line=5, target_content="a", replacement_content="b"
    )
    pfile = PatchFile(file_path="main.py", chunks=(chunk,))
    patch = ExecutionPatch(patch_id="p1", files=(pfile,))

    val = svc.validate_patch(patch)
    assert val.is_valid
    assert val.syntax_valid
