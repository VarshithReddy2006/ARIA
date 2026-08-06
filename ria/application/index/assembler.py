"""Index Batch Assembler."""

from collections import Counter
from collections.abc import Sequence

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.units import IndexBatch, IndexManifest, ParseUnit
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


class IndexBatchAssembler:
    """Assembler creating immutable IndexBatch and IndexManifest from a sequence of ParseUnits."""

    def assemble_batch(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        parse_units: Sequence[ParseUnit],
        created_at: Timestamp,
    ) -> tuple[IndexBatch, IndexManifest]:
        """Assemble immutable IndexBatch and its corresponding IndexManifest descriptor."""
        batch_id = UUIDv4.generate()
        tuple_units = tuple(parse_units)

        total_files = len(tuple_units)
        total_parsed = sum(1 for pu in tuple_units if pu.ast_unit is not None)
        total_failed = total_files - total_parsed

        lang_counts: Counter[str] = Counter()
        for pu in tuple_units:
            lang_counts[pu.file_unit.language.value] += 1

        manifest = IndexManifest(
            batch_id=batch_id,
            total_files=total_files,
            total_parsed=total_parsed,
            total_failed=total_failed,
            language_counts=tuple((lang, count) for lang, count in lang_counts.items()),
        )

        batch = IndexBatch(
            batch_id=batch_id,
            repo_id=repo_id,
            commit=commit,
            parse_units=tuple_units,
            created_at=created_at,
        )

        return batch, manifest
