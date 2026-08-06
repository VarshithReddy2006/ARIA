"""Change detection.

A single pure function comparing two ``path -> content_hash`` mappings. No I/O, no
collaborators, no configuration — which is why it is testable in microseconds and
why the same implementation serves ingestion now and pull request diffing later.

Rename detection
----------------
Content addressing gives exact rename detection for free: if a path disappeared, a
different path appeared, and both hold the same content hash, the file moved. No
similarity threshold is involved, so the result carries no uncertainty and needs no
confidence value — which matters because :class:`~ria.domain.models.change_set.ChangeSet`
deliberately has no field for one.

The rule is narrower than git's ``-M`` heuristic, which also detects a rename when
content changed slightly. That case is reported here as a deletion plus an addition.
The trade is deliberate: a rename claimed here means the parse cache is definitely
reusable, whereas a similarity-based rename would not, and would silently skip a
reparse the content actually required.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Set

from ria.domain.models.change_set import ChangeSet, RenamedPath

__all__ = ["compute_change_set"]


def compute_change_set(
    *,
    head_sha: str,
    current: Mapping[str, str],
    previous: Optional[Mapping[str, str]] = None,
    base_sha: Optional[str] = None,
    detect_renames: bool = True,
) -> ChangeSet:
    """Compare two commit trees by content hash.

    Args:
        head_sha: Commit the ``current`` mapping describes.
        current: Path to canonical content hash for the head commit.
        previous: Path to canonical content hash for the base commit. ``None``
            means there is no base, so every path is an addition.
        base_sha: Commit the ``previous`` mapping describes. Required when
            ``previous`` is supplied, because a change set that cannot name its
            base is not interpretable.
        detect_renames: Whether to pair deletions with additions that share a
            content hash. Disabling it reports both sides separately, which is
            occasionally wanted when a caller must treat every new path as new.

    Returns:
        The change set. Categories are disjoint.

    Raises:
        ValueError: If ``previous`` is supplied without ``base_sha``, or if
            ``base_sha`` is supplied without ``previous``.
    """
    if previous is None and base_sha is not None:
        raise ValueError("base_sha requires a previous mapping")
    if previous is not None and base_sha is None:
        raise ValueError("a previous mapping requires base_sha")

    if previous is None:
        return ChangeSet(head_sha=head_sha, base_sha=None, added=frozenset(current))

    current_paths: Set[str] = set(current)
    previous_paths: Set[str] = set(previous)

    added: Set[str] = current_paths - previous_paths
    deleted: Set[str] = previous_paths - current_paths
    modified: Set[str] = {
        path
        for path in current_paths & previous_paths
        if current[path] != previous[path]
    }

    renamed: List[RenamedPath] = []
    if detect_renames and added and deleted:
        renamed = _pair_renames(added, deleted, current, previous)

    return ChangeSet(
        head_sha=head_sha,
        base_sha=base_sha,
        added=frozenset(added),
        modified=frozenset(modified),
        deleted=frozenset(deleted),
        renamed=tuple(renamed),
    )


def _pair_renames(
    added: Set[str],
    deleted: Set[str],
    current: Mapping[str, str],
    previous: Mapping[str, str],
) -> List[RenamedPath]:
    """Pair deleted paths with added paths sharing a content hash.

    Mutates ``added`` and ``deleted`` in place, removing every path that was paired,
    so the caller's categories remain disjoint.

    Pairing is deterministic: candidates on both sides are sorted by path before
    matching, so a tree where two files were deleted and two identical files added
    produces the same pairing on every run. Non-deterministic pairing would make the
    change set unstable across runs and break the response caching of SDD section
    5.5.

    A hash present in ``previous`` at a path that still exists in ``current`` is not
    a rename candidate: that is a copy, and reporting it as a rename would claim the
    original was removed when it was not.

    Args:
        added: Paths present only in the head commit. Mutated.
        deleted: Paths present only in the base commit. Mutated.
        current: Head commit mapping.
        previous: Base commit mapping.

    Returns:
        The detected renames.
    """
    deleted_by_hash: Dict[str, List[str]] = {}
    for path in sorted(deleted):
        deleted_by_hash.setdefault(previous[path], []).append(path)

    renamed: List[RenamedPath] = []
    for new_path in sorted(added):
        content_hash = current[new_path]
        candidates = deleted_by_hash.get(content_hash)
        if not candidates:
            continue
        old_path = candidates.pop(0)
        renamed.append(
            RenamedPath(
                previous_path=old_path,
                current_path=new_path,
                content_hash=content_hash,
            )
        )

    for rename in renamed:
        added.discard(rename.current_path)
        deleted.discard(rename.previous_path)
    return renamed
