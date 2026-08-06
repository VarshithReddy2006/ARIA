"""Tests for the file unit entity and the commit manifest."""

from __future__ import annotations

import dataclasses

import pytest

from ria.domain.enums import FileClassification, LanguageTier, ParseStatus
from ria.domain.errors import InvalidPathError
from ria.domain.identity import CommitSha, ContentHash, Moniker, RepositoryId
from ria.domain.language import UNKNOWN_LANGUAGE
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.manifest import CommitManifest
from tests.ria.conftest import utc

SHA = CommitSha("a" * 40)
PARENT = CommitSha("b" * 40)
CREATED = utc(2026, 1, 1, 12)


def make_unit(**overrides) -> FileUnit:
    """Build a file unit with sensible defaults for a test.

    Args:
        **overrides: Fields to replace.

    Returns:
        A valid pending file unit unless overridden.
    """
    defaults = dict(
        repository_id=RepositoryId.generate(),
        commit_sha=SHA,
        path="src/a.py",
        content_hash=ContentHash.of_bytes(b"payload"),
        blob_sha="c" * 40,
        language="python",
        language_tier=LanguageTier.NONE,
        size_bytes=7,
        line_count=1,
        classification=FileClassification.SOURCE,
    )
    defaults.update(overrides)
    return FileUnit(**defaults)


class TestConstruction:
    """Invariants enforced when a file unit is constructed."""

    def test_normalises_the_path_on_construction(self) -> None:
        """One file has one identity regardless of how its path was spelled."""
        unit = make_unit(path=".\\src\\\\a.py")
        assert unit.path == "src/a.py"

    def test_rejects_an_escaping_path(self) -> None:
        """A path leaving the repository root is refused, not resolved."""
        with pytest.raises(InvalidPathError):
            make_unit(path="../secrets.env")

    def test_rejects_a_missing_blob_sha(self) -> None:
        """The git object name is retained so content can be re-read from the mirror."""
        with pytest.raises(ValueError, match="blob_sha"):
            make_unit(blob_sha="")

    def test_rejects_a_blank_language(self) -> None:
        """Absence of a detected language is the unknown sentinel, not an empty string."""
        with pytest.raises(ValueError, match="unknown sentinel"):
            make_unit(language="")

    @pytest.mark.parametrize("field,value", [("size_bytes", -1), ("line_count", -1)])
    def test_rejects_negative_measures(self, field: str, value: int) -> None:
        """Negative sizes and line counts are impossible."""
        with pytest.raises(ValueError):
            make_unit(**{field: value})

    @pytest.mark.parametrize("status", [ParseStatus.UNPARSEABLE, ParseStatus.SKIPPED])
    def test_requires_a_reason_for_a_coverage_gap(self, status: ParseStatus) -> None:
        """Every coverage gap states its cause.

        PRD principle P11 forbids silent degradation, and an unexplained skipped
        file is exactly that: coverage is missing and nothing says why.
        """
        with pytest.raises(ValueError, match="parse_status_reason is mandatory"):
            make_unit(parse_status=status)

    def test_permits_an_absent_reason_for_a_successful_parse(self) -> None:
        """A successful parse needs no explanation."""
        assert make_unit(parse_status=ParseStatus.PARSED).parse_status_reason is None

    def test_defaults_to_pending_parse_status(self) -> None:
        """A unit created during ingestion has not been parsed yet.

        Recording it as ``SKIPPED`` would be a false statement about coverage, which
        is why the ``PENDING`` member exists.
        """
        assert make_unit().parse_status is ParseStatus.PENDING

    def test_line_count_may_be_unmeasured(self) -> None:
        """Binary and skipped content has no line count, which is not zero."""
        unit = make_unit(
            classification=FileClassification.BINARY,
            line_count=None,
            language="unknown",
        )
        assert unit.line_count is None

    def test_is_immutable(self) -> None:
        """Fields cannot be assigned; change is expressed by transformation."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            make_unit().path = "other.py"  # type: ignore[misc]


class TestIdentity:
    """Logical and physical identity of a file unit."""

    def test_moniker_is_derived_from_the_normalised_path(self) -> None:
        """Logical identity follows the canonical path, never the raw input."""
        unit = make_unit(path="./src/a.py")
        assert str(unit.moniker) == "file:.:src/a.py"

    def test_directory_of_a_root_level_file_is_empty(self) -> None:
        """The empty string denotes the root module, which is a valid identity."""
        assert make_unit(path="setup.py").directory == ""

    def test_directory_of_a_nested_file(self) -> None:
        """A nested file reports its immediate parent."""
        assert make_unit(path="src/deep/a.py").directory == "src/deep"

    def test_reuse_key_combines_content_and_language(self) -> None:
        """The reuse key is the parse cache key of Twin Spec section 6.4."""
        unit = make_unit()
        assert unit.reuse_key == f"{unit.content_hash}|python"

    def test_identical_content_at_two_paths_shares_a_reuse_key(self) -> None:
        """Duplicated content is parsed once, however many paths hold it."""
        first = make_unit(path="src/a.py")
        second = make_unit(path="src/copy/a.py")
        assert first.reuse_key == second.reuse_key
        assert first.moniker != second.moniker

    def test_reuse_key_separates_languages(self) -> None:
        """The same bytes read as two languages are two parse results."""
        payload = ContentHash.of_bytes(b"shared")
        python = make_unit(content_hash=payload, language="python")
        javascript = make_unit(content_hash=payload, language="javascript")
        assert python.reuse_key != javascript.reuse_key


class TestPredicates:
    """Behavioural rules driven by classification and language."""

    def test_source_with_a_language_is_a_parse_candidate(self) -> None:
        """A recognised source file is offered to the parser layer."""
        assert make_unit().is_parse_candidate is True

    def test_unknown_language_is_not_a_parse_candidate(self) -> None:
        """A file with no detected language has no grammar to parse it."""
        assert make_unit(language=UNKNOWN_LANGUAGE).is_parse_candidate is False

    def test_binary_is_not_a_parse_candidate(self) -> None:
        """Binary content is never parsed."""
        assert (
            make_unit(classification=FileClassification.BINARY).is_parse_candidate
            is False
        )

    def test_vendored_is_a_candidate_but_not_measured(self) -> None:
        """Vendored code resolves symbols yet stays out of metrics."""
        unit = make_unit(classification=FileClassification.VENDORED)
        assert unit.is_parse_candidate is True
        assert unit.counts_toward_metrics is False

    def test_a_candidate_may_still_have_no_extractor(self) -> None:
        """Recognised and understood are different claims.

        A candidate with tier ``NONE`` is a file we know the language of and cannot
        yet extract from, which is what coverage must report honestly.
        """
        unit = make_unit(language_tier=LanguageTier.NONE)
        assert unit.is_parse_candidate is True
        assert unit.language_tier is LanguageTier.NONE


class TestTransformations:
    """Functional updates to a file unit."""

    def test_records_a_parse_outcome(self) -> None:
        """A parse result is attached without mutating the original."""
        unit = make_unit()
        parsed = unit.with_parse_outcome(ParseStatus.PARSED)
        assert parsed.parse_status is ParseStatus.PARSED
        assert unit.parse_status is ParseStatus.PENDING

    def test_records_a_failure_with_its_reason(self) -> None:
        """An unparseable file carries its cause forward."""
        unit = make_unit().with_parse_outcome(
            ParseStatus.UNPARSEABLE, reason="syntax error at line 4"
        )
        assert unit.parse_status_reason == "syntax error at line 4"

    def test_rejects_a_failure_without_a_reason(self) -> None:
        """The construction invariant applies to transformations too."""
        with pytest.raises(ValueError):
            make_unit().with_parse_outcome(ParseStatus.SKIPPED)

    def test_attaches_a_module(self) -> None:
        """Module attachment is available for Milestone 5 without a schema change."""
        module = Moniker.for_module("src")
        assert make_unit().with_module(module).module_moniker == module


class TestCommitManifest:
    """The boundary artefact between ingestion and every layer above it."""

    def make_manifest(self, *paths: str, **overrides) -> CommitManifest:
        """Build a manifest containing one unit per supplied path.

        Args:
            *paths: Paths to include.
            **overrides: Manifest fields to replace.

        Returns:
            A valid manifest.
        """
        repository_id = overrides.pop("repository_id", RepositoryId.generate())
        tree = tuple(
            make_unit(
                repository_id=repository_id,
                path=path,
                content_hash=ContentHash.of_bytes(path.encode()),
            )
            for path in paths
        )
        defaults = dict(
            repository_id=repository_id,
            commit_sha=SHA,
            parent_shas=(PARENT,),
            tree=tree,
            created_at=CREATED,
        )
        defaults.update(overrides)
        return CommitManifest(**defaults)

    def test_orders_the_tree_by_path(self) -> None:
        """A manifest is deterministically ordered regardless of input order.

        Determinism is required for the response caching of SDD section 5.5: two
        identical ingestions must produce byte-identical output.
        """
        manifest = self.make_manifest("src/z.py", "src/a.py", "README.md")
        assert [unit.path for unit in manifest.tree] == [
            "README.md",
            "src/a.py",
            "src/z.py",
        ]

    def test_rejects_a_duplicate_path(self) -> None:
        """One path may appear once, or the path index would silently lose an entry."""
        repository_id = RepositoryId.generate()
        unit = make_unit(repository_id=repository_id, path="src/a.py")
        with pytest.raises(ValueError, match="duplicate path"):
            CommitManifest(
                repository_id=repository_id,
                commit_sha=SHA,
                parent_shas=(),
                tree=(unit, unit),
                created_at=CREATED,
            )

    def test_rejects_a_unit_from_another_commit(self) -> None:
        """A manifest describes exactly one commit.

        Mixing commits would produce a tree that never existed, and every fact
        derived from it would be attributed to the wrong commit.
        """
        repository_id = RepositoryId.generate()
        foreign = make_unit(repository_id=repository_id, commit_sha=PARENT)
        with pytest.raises(ValueError, match="belongs to commit"):
            CommitManifest(
                repository_id=repository_id,
                commit_sha=SHA,
                parent_shas=(),
                tree=(foreign,),
                created_at=CREATED,
            )

    def test_rejects_a_unit_from_another_repository(self) -> None:
        """A manifest describes exactly one repository."""
        foreign = make_unit(repository_id=RepositoryId.generate())
        with pytest.raises(ValueError, match="different repository"):
            CommitManifest(
                repository_id=RepositoryId.generate(),
                commit_sha=SHA,
                parent_shas=(),
                tree=(foreign,),
                created_at=CREATED,
            )

    def test_path_lookup_is_indexed(self) -> None:
        """Lookup is by index, which keeps Milestone 2's diff linear."""
        manifest = self.make_manifest("src/a.py", "src/b.py")
        assert manifest.get("src/a.py") is not None
        assert manifest.get("missing.py") is None
        assert manifest.paths() == frozenset({"src/a.py", "src/b.py"})

    def test_content_hash_map_is_the_diff_input(self) -> None:
        """Change detection compares two of these maps without reading a file."""
        manifest = self.make_manifest("src/a.py", "src/b.py")
        hashes = manifest.content_hashes()
        assert set(hashes) == {"src/a.py", "src/b.py"}
        assert hashes["src/a.py"] == ContentHash.of_bytes(b"src/a.py")

    def test_distinct_content_hashes_deduplicate(self) -> None:
        """Duplicated content is stored and parsed once."""
        repository_id = RepositoryId.generate()
        shared = ContentHash.of_bytes(b"same")
        tree = (
            make_unit(repository_id=repository_id, path="a.py", content_hash=shared),
            make_unit(repository_id=repository_id, path="b.py", content_hash=shared),
        )
        manifest = CommitManifest(
            repository_id=repository_id,
            commit_sha=SHA,
            parent_shas=(),
            tree=tree,
            created_at=CREATED,
        )
        assert len(manifest.distinct_content_hashes()) == 1
        assert manifest.file_count == 2

    def test_aggregates_size_and_merge_status(self) -> None:
        """Aggregate counters are derived rather than stored."""
        manifest = self.make_manifest("a.py", "b.py")
        assert manifest.total_bytes == 14
        assert manifest.is_merge is False
        assert self.make_manifest("a.py", parent_shas=(PARENT, SHA)).is_merge is True

    def test_filters_by_classification(self) -> None:
        """Units are selectable by role for classification-specific work."""
        repository_id = RepositoryId.generate()
        tree = (
            make_unit(
                repository_id=repository_id,
                path="src/a.py",
                classification=FileClassification.SOURCE,
            ),
            make_unit(
                repository_id=repository_id,
                path="tests/test_a.py",
                classification=FileClassification.TEST,
            ),
        )
        manifest = CommitManifest(
            repository_id=repository_id,
            commit_sha=SHA,
            parent_shas=(),
            tree=tree,
            created_at=CREATED,
        )
        assert len(manifest.units_by_classification(FileClassification.TEST)) == 1

    def test_parse_candidates_exclude_unparseable_roles(self) -> None:
        """Only candidates are offered to the parser layer."""
        repository_id = RepositoryId.generate()
        tree = (
            make_unit(repository_id=repository_id, path="src/a.py"),
            make_unit(
                repository_id=repository_id,
                path="logo.png",
                classification=FileClassification.BINARY,
                language=UNKNOWN_LANGUAGE,
                line_count=None,
            ),
        )
        manifest = CommitManifest(
            repository_id=repository_id,
            commit_sha=SHA,
            parent_shas=(),
            tree=tree,
            created_at=CREATED,
        )
        assert [unit.path for unit in manifest.parse_candidates()] == ["src/a.py"]

    def test_language_line_counts_exclude_unmeasured_and_vendored(self) -> None:
        """Vendored code and unmeasured files contribute nothing to language totals.

        This is where the classification rules pay off: a repository whose bulk is
        ``node_modules`` reports its own languages, not its dependencies'.
        """
        repository_id = RepositoryId.generate()
        tree = (
            make_unit(repository_id=repository_id, path="src/a.py", line_count=10),
            make_unit(repository_id=repository_id, path="src/b.py", line_count=5),
            make_unit(
                repository_id=repository_id,
                path="node_modules/pkg/index.js",
                language="javascript",
                classification=FileClassification.VENDORED,
                line_count=9000,
            ),
            make_unit(repository_id=repository_id, path="src/c.py", line_count=None),
        )
        manifest = CommitManifest(
            repository_id=repository_id,
            commit_sha=SHA,
            parent_shas=(),
            tree=tree,
            created_at=CREATED,
        )
        assert manifest.language_line_counts() == {"python": 15}

    def test_truncation_is_representable_and_defaults_to_false(self) -> None:
        """A truncated manifest is detectable rather than silently partial.

        SDD section 3 requires rejection over partial ingestion; the flag exists so
        an accidental partial manifest is caught, not so one may be produced.
        """
        assert self.make_manifest("a.py").truncated is False
        assert self.make_manifest("a.py", truncated=True).truncated is True

    def test_empty_tree_is_valid(self) -> None:
        """A commit whose tree holds no eligible files is representable."""
        manifest = self.make_manifest()
        assert manifest.file_count == 0
        assert manifest.total_bytes == 0
        assert manifest.language_line_counts() == {}
