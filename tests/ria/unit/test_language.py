"""Tests for the language and classification catalogue.

Classification drives correctness far beyond cosmetics. Twin Spec section 3.2
requires vendored and generated code to be excluded from metrics while remaining
available to dependency resolution, so a misclassification silently corrupts every
health figure the platform reports.
"""

from __future__ import annotations

import pytest

from ria.domain.enums import FileClassification, LanguageTier, ResolutionMethod
from ria.domain.language import (
    DEFAULT_LANGUAGE_CATALOGUE,
    UNKNOWN_LANGUAGE,
    LanguageCatalogue,
    LanguageDescriptor,
)

CATALOGUE = DEFAULT_LANGUAGE_CATALOGUE


class TestDetection:
    """Language detection from a path."""

    @pytest.mark.parametrize(
        "path,language",
        [
            ("src/a.py", "python"),
            ("src/a.pyi", "python"),
            ("src/a.js", "javascript"),
            ("src/a.mjs", "javascript"),
            ("src/a.ts", "typescript"),
            ("src/a.tsx", "tsx"),
            ("Main.java", "java"),
            ("main.go", "go"),
            ("README.md", "markdown"),
            ("pyproject.toml", "toml"),
            ("Dockerfile", "dockerfile"),
            ("Makefile", "make"),
            ("mystery.qqq", UNKNOWN_LANGUAGE),
            ("noextension", UNKNOWN_LANGUAGE),
        ],
    )
    def test_detects_language(self, path: str, language: str) -> None:
        """Extension and exact-filename rules both resolve a language."""
        assert CATALOGUE.detect_language(path) == language

    def test_detection_is_case_insensitive(self) -> None:
        """A path's case must not change its identity."""
        assert CATALOGUE.detect_language("SRC/A.PY") == "python"
        assert CATALOGUE.detect_language("DOCKERFILE") == "dockerfile"

    def test_tsx_is_distinct_from_typescript(self) -> None:
        """TSX has its own grammar and therefore its own catalogue entry."""
        assert CATALOGUE.detect_language("a.tsx") != CATALOGUE.detect_language("a.ts")


class TestTierDeclaration:
    """Declared extraction capability per language."""

    def test_every_language_declares_none_at_milestone_one(self) -> None:
        """No extractor exists yet, so no language may claim a tier.

        PRD principle P8 forbids a capability claim without a measurement. A tier
        promoted before its extractor and precision tests land would be exactly
        such a claim, so this test guards the honesty of the catalogue.
        """
        for descriptor in CATALOGUE.descriptors:
            assert descriptor.tier is LanguageTier.NONE, descriptor.name

    def test_unknown_language_has_no_tier(self) -> None:
        """An uncatalogued language reports no extraction capability."""
        assert CATALOGUE.tier_for("brainfuck") is LanguageTier.NONE

    def test_tier_bounds_the_resolution_method(self) -> None:
        """Tier A cannot reach exact resolution; only tier B can.

        This is the link between the parser layer's capability and the confidence a
        relation may claim in Milestone 4.
        """
        assert LanguageTier.TIER_A.best_resolution_method is ResolutionMethod.HEURISTIC
        assert LanguageTier.TIER_B.best_resolution_method is ResolutionMethod.EXACT

    def test_describe_returns_none_for_unknown(self) -> None:
        """Describing an uncatalogued language returns nothing rather than raising."""
        assert CATALOGUE.describe("brainfuck") is None
        assert CATALOGUE.describe("python") is not None


class TestClassificationPrecedence:
    """Ordering of the classification rules."""

    @pytest.mark.parametrize(
        "path,classification",
        [
            ("src/a.py", FileClassification.SOURCE),
            ("README.md", FileClassification.DOC),
            ("pyproject.toml", FileClassification.CONFIG),
            ("logo.png", FileClassification.BINARY),
            ("mystery.qqq", FileClassification.UNKNOWN),
        ],
    )
    def test_extension_default(
        self, path: str, classification: FileClassification
    ) -> None:
        """With no higher rule matching, the language default applies."""
        assert CATALOGUE.classify(path) is classification

    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_a.py",
            "src/a_test.go",
            "src/a.test.ts",
            "spec/thing_spec.rb",
            "src/__tests__/a.js",
            "conftest.py",
        ],
    )
    def test_test_conventions(self, path: str) -> None:
        """Test trees and filename conventions classify as tests."""
        assert CATALOGUE.classify(path) is FileClassification.TEST

    def test_does_not_mistake_similar_stems_for_tests(self) -> None:
        """A stem merely ending in ``test`` is not a test file.

        ``latest.py`` would be misclassified by a naive suffix check, which would
        remove a real source file from every metric.
        """
        assert CATALOGUE.classify("src/latest.py") is FileClassification.SOURCE
        assert CATALOGUE.classify("src/protest.py") is FileClassification.SOURCE

    @pytest.mark.parametrize(
        "path",
        [
            "node_modules/pkg/index.js",
            "vendor/lib/a.go",
            "third_party/x/a.py",
            ".venv/lib/site-packages/x.py",
        ],
    )
    def test_vendored_outranks_everything_below_it(self, path: str) -> None:
        """Vendored code is vendored even when it looks like source or a test."""
        assert CATALOGUE.classify(path) is FileClassification.VENDORED

    def test_vendored_outranks_test_convention(self) -> None:
        """A test file inside a vendored tree is vendored, not a test.

        Precedence matters here: counting a dependency's own test suite as the
        repository's tests would inflate every coverage and hygiene figure.
        """
        assert (
            CATALOGUE.classify("node_modules/pkg/tests/test_a.py")
            is FileClassification.VENDORED
        )

    @pytest.mark.parametrize(
        "path",
        [
            "dist/bundle.js",
            "build/out.py",
            "src/__pycache__/a.py",
            "src/app.min.js",
            "src/service_pb2.py",
            "src/types.d.ts",
        ],
    )
    def test_generated_markers(self, path: str) -> None:
        """Build trees and generated-file markers classify as generated."""
        assert CATALOGUE.classify(path) is FileClassification.GENERATED

    @pytest.mark.parametrize(
        "path", ["package-lock.json", "poetry.lock", "go.sum", "yarn.lock"]
    )
    def test_lock_files_are_config_not_source(self, path: str) -> None:
        """Lock files are configuration, so they never enter source metrics."""
        assert CATALOGUE.classify(path) is FileClassification.CONFIG

    def test_binary_outranks_vendoring(self) -> None:
        """Binary content is never parseable regardless of where it sits."""
        assert (
            CATALOGUE.classify("node_modules/pkg/icon.png") is FileClassification.BINARY
        )


class TestClassificationConsequences:
    """The behavioural rules that classification exists to drive."""

    @pytest.mark.parametrize(
        "classification,counts",
        [
            (FileClassification.SOURCE, True),
            (FileClassification.TEST, True),
            (FileClassification.VENDORED, False),
            (FileClassification.GENERATED, False),
            (FileClassification.CONFIG, False),
            (FileClassification.DOC, False),
            (FileClassification.BINARY, False),
            (FileClassification.UNKNOWN, False),
        ],
    )
    def test_metric_participation(
        self, classification: FileClassification, counts: bool
    ) -> None:
        """Only source and test files contribute to health and churn metrics."""
        assert classification.counts_toward_metrics is counts

    def test_vendored_is_parseable_but_not_measured(self) -> None:
        """Vendored code is parsed for resolution yet excluded from metrics.

        This pair of properties is the whole point of separating the two questions:
        a dependency's symbols must resolve, and its debt is not ours.
        """
        assert FileClassification.VENDORED.is_parseable_candidate is True
        assert FileClassification.VENDORED.counts_toward_metrics is False

    def test_binary_and_config_are_never_parsed(self) -> None:
        """Content with no grammar is not offered to the parser layer."""
        assert FileClassification.BINARY.is_parseable_candidate is False
        assert FileClassification.CONFIG.is_parseable_candidate is False


class TestCatalogueConstruction:
    """Guards on building a catalogue."""

    def test_rejects_duplicate_extension_claims(self) -> None:
        """Two languages claiming one extension would make detection ambiguous."""
        with pytest.raises(ValueError, match="claimed by both"):
            LanguageCatalogue(
                (
                    LanguageDescriptor(
                        name="first",
                        extensions=(".zz",),
                        tier=LanguageTier.NONE,
                        default_classification=FileClassification.SOURCE,
                    ),
                    LanguageDescriptor(
                        name="second",
                        extensions=(".zz",),
                        tier=LanguageTier.NONE,
                        default_classification=FileClassification.SOURCE,
                    ),
                )
            )

    def test_rejects_duplicate_filename_claims(self) -> None:
        """Exact-filename rules must also be unambiguous."""
        with pytest.raises(ValueError, match="claimed by both"):
            LanguageCatalogue(
                (
                    LanguageDescriptor(
                        name="first",
                        extensions=(".aa",),
                        tier=LanguageTier.NONE,
                        default_classification=FileClassification.CONFIG,
                        filenames=("shared",),
                    ),
                    LanguageDescriptor(
                        name="second",
                        extensions=(".bb",),
                        tier=LanguageTier.NONE,
                        default_classification=FileClassification.CONFIG,
                        filenames=("shared",),
                    ),
                )
            )

    @pytest.mark.parametrize("extension", ["py", ".PY"])
    def test_rejects_malformed_extensions(self, extension: str) -> None:
        """Extensions must be lowercase and dot-prefixed so lookup is exact."""
        with pytest.raises(ValueError):
            LanguageDescriptor(
                name="x",
                extensions=(extension,),
                tier=LanguageTier.NONE,
                default_classification=FileClassification.SOURCE,
            )

    def test_rejects_uppercase_filenames(self) -> None:
        """Filenames are matched lowercased, so they must be declared lowercase."""
        with pytest.raises(ValueError):
            LanguageDescriptor(
                name="x",
                extensions=(".x",),
                tier=LanguageTier.NONE,
                default_classification=FileClassification.CONFIG,
                filenames=("Dockerfile",),
            )

    def test_default_catalogue_is_internally_consistent(self) -> None:
        """The shipped catalogue has unique names and builds without conflict."""
        names = [descriptor.name for descriptor in CATALOGUE.descriptors]
        assert len(names) == len(set(names))
