"""Patch Generator application service.

Generates unified multi-file patches and incremental patch metadata.
Implements :class:`~ria.ports.execution.PatchGenerationPort`.
"""

from __future__ import annotations

import hashlib
from typing import List, Tuple

from ria.domain.models.patch_models import (
    ExecutionPatch,
    PatchChunk,
    PatchFile,
    PatchStatistics,
)
from ria.domain.models.repository_edit_models import RepositoryEdit
from ria.ports.execution import PatchGenerationPort

__all__ = ["PatchGeneratorService"]


class PatchGeneratorService(PatchGenerationPort):
    """Service for constructing unified ExecutionPatch objects."""

    def generate_patch(
        self,
        edits: Tuple[RepositoryEdit, ...],
    ) -> ExecutionPatch:
        """Construct ExecutionPatch from edits."""
        patch_files: List[PatchFile] = []
        total_insertions = 0
        total_deletions = 0

        for edit in edits:
            lines = edit.new_content.splitlines() if edit.new_content else []
            num_lines = len(lines)

            chunk = PatchChunk(
                start_line=1,
                end_line=max(1, num_lines),
                target_content="",
                replacement_content=edit.new_content,
            )
            patch_files.append(PatchFile(file_path=edit.file_path, chunks=(chunk,)))
            total_insertions += num_lines

        stats = PatchStatistics(
            files_changed=len(edits),
            insertions=total_insertions,
            deletions=total_deletions,
        )

        digest = hashlib.sha256(f"patch_gen_{len(edits)}".encode("utf-8")).hexdigest()[
            :16
        ]

        return ExecutionPatch(
            patch_id=f"gen_{digest}",
            files=tuple(patch_files),
            statistics=stats,
        )
