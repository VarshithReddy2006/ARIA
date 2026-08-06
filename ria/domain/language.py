"""Table-driven language and file classification catalogue.

SDD section 3 (L1, Extensibility) requires that "language classification is
table-driven". This module is that table plus the lookup logic. It answers three
questions about a path, before any content is read:

1. Which language is this file written in?
2. Which extraction tier is available for that language, and therefore what is
   the best :class:`~ria.domain.enums.ResolutionMethod` its relations can reach?
3. What is the file's :class:`~ria.domain.enums.FileClassification`?

Question 2 is the one that matters strategically. PRD principle P8 forbids
claiming support for a language without a measured precision figure, and
:attr:`LanguageDescriptor.tier` is where that ceiling is declared. A language
present in this table with ``LanguageTier.NONE`` is recognised but explicitly
not understood, which is the honest representation demanded by P11.

Classification precedence
-------------------------
Classification is decided by the first matching rule, in this order:

1. Vendored or generated *directory* markers, because a vendored file that also
   looks like source is still vendored and must not enter metrics.
2. Generated-file name markers.
3. Test path and filename conventions.
4. Extension-derived classification from the language table.

Ordering matters: a test file inside ``node_modules`` is vendored, not a test.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple

from ria.domain.enums import FileClassification, LanguageTier

__all__ = [
    "LanguageDescriptor",
    "LanguageCatalogue",
    "DEFAULT_LANGUAGE_CATALOGUE",
    "UNKNOWN_LANGUAGE",
]

#: Canonical name used when no descriptor matches a path.
UNKNOWN_LANGUAGE = "unknown"


@dataclass(frozen=True)
class LanguageDescriptor:
    """Declared capability for one language.

    Attributes:
        name: Canonical language name, used as a metrics label and as the key of
            per-language coverage and precision reporting.
        extensions: Lowercase file extensions including the leading dot.
        tier: Extraction tier currently available. Declares the precision
            ceiling for this language; see SDD section 3 (L2).
        default_classification: Classification applied to files of this language
            when no higher-precedence rule matches.
        filenames: Exact lowercase filenames that map to this language
            regardless of extension, for example ``dockerfile`` or ``makefile``.
    """

    name: str
    extensions: Tuple[str, ...]
    tier: LanguageTier
    default_classification: FileClassification
    filenames: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for extension in self.extensions:
            if not extension.startswith(".") or extension != extension.lower():
                raise ValueError(
                    f"extension must be lowercase and start with a dot: {extension!r}"
                )
        for filename in self.filenames:
            if filename != filename.lower():
                raise ValueError(f"filename must be lowercase: {filename!r}")


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------
# Tier assignment reflects what is *implemented*, not what is planned. Every
# language here is TIER_NONE at Milestone 1 because no extractor exists yet;
# Milestone 3 promotes languages to TIER_A as tree-sitter grammars and query
# sets land with fixture-backed precision tests, and Milestone 4 promotes to
# TIER_B as SCIP indexers are integrated. Declaring a tier before the extractor
# exists would violate PRD principle P8.

_LANGUAGES: Tuple[LanguageDescriptor, ...] = (
    LanguageDescriptor(
        name="python",
        extensions=(".py", ".pyi"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="javascript",
        extensions=(".js", ".jsx", ".mjs", ".cjs"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="typescript",
        extensions=(".ts", ".mts", ".cts"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="tsx",
        extensions=(".tsx",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="java",
        extensions=(".java",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="go",
        extensions=(".go",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="csharp",
        extensions=(".cs",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="kotlin",
        extensions=(".kt", ".kts"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="rust",
        extensions=(".rs",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="ruby",
        extensions=(".rb",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="php",
        extensions=(".php",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="c",
        extensions=(".c", ".h"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="cpp",
        extensions=(".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="scala",
        extensions=(".scala", ".sc"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="swift",
        extensions=(".swift",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="shell",
        extensions=(".sh", ".bash", ".zsh"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="sql",
        extensions=(".sql",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="html",
        extensions=(".html", ".htm"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="css",
        extensions=(".css", ".scss", ".sass", ".less"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.SOURCE,
    ),
    LanguageDescriptor(
        name="markdown",
        extensions=(".md", ".mdx", ".rst", ".adoc"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.DOC,
    ),
    LanguageDescriptor(
        name="json",
        extensions=(".json", ".jsonc"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
    ),
    LanguageDescriptor(
        name="yaml",
        extensions=(".yaml", ".yml"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
    ),
    LanguageDescriptor(
        name="toml",
        extensions=(".toml",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
    ),
    LanguageDescriptor(
        name="ini",
        extensions=(".ini", ".cfg", ".conf", ".properties"),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
    ),
    LanguageDescriptor(
        name="xml",
        extensions=(".xml",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
    ),
    LanguageDescriptor(
        name="dockerfile",
        extensions=(".dockerfile",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
        filenames=("dockerfile",),
    ),
    LanguageDescriptor(
        name="make",
        extensions=(".mk",),
        tier=LanguageTier.NONE,
        default_classification=FileClassification.CONFIG,
        filenames=("makefile",),
    ),
)

#: Extensions whose contents are not text and must never be parsed or embedded.
_BINARY_EXTENSIONS: Tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".svgz",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".lib",
    ".class",
    ".jar",
    ".war",
    ".pyc",
    ".pyo",
    ".pyd",
    ".wasm",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wav",
    ".webm",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".parquet",
    ".pkl",
    ".pickle",
    ".npy",
)

#: Path segments that mark third-party code checked into the repository.
_VENDORED_SEGMENTS: Tuple[str, ...] = (
    "node_modules",
    "vendor",
    "third_party",
    "thirdparty",
    "external",
    "site-packages",
    "bower_components",
    ".venv",
    "venv",
    "virtualenv",
)

#: Path segments that mark build output or machine-produced trees.
_GENERATED_SEGMENTS: Tuple[str, ...] = (
    "dist",
    "build",
    "out",
    "target",
    "__pycache__",
    ".next",
    ".nuxt",
    "coverage",
    "generated",
    "gen",
    "migrations_autogen",
)

#: Filename markers that indicate a machine-produced file.
_GENERATED_MARKERS: Tuple[str, ...] = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    "_pb2.py",
    "_pb2_grpc.py",
    ".pb.go",
    ".g.dart",
    ".generated.ts",
    ".d.ts",
)

#: Exact lowercase filenames that are lock files: config, never source.
_LOCK_FILENAMES: Tuple[str, ...] = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
    "go.sum",
)

#: Path segments that mark a test tree.
_TEST_SEGMENTS: Tuple[str, ...] = (
    "test",
    "tests",
    "spec",
    "specs",
    "__tests__",
    "testing",
)

#: Filename prefixes that mark a test file, for example ``test_parser.py``.
_TEST_FILENAME_PREFIXES: Tuple[str, ...] = ("test_", "spec_")

#: Filename stem suffixes that mark a test file, for example ``parser_test.go``
#: or ``parser.test.ts``. Bare ``test`` is deliberately excluded: it would
#: misclassify unrelated stems such as ``latest``.
_TEST_FILENAME_SUFFIXES: Tuple[str, ...] = ("_test", "_spec", ".test", ".spec")

#: Filename stems that are themselves a test marker.
_TEST_FILENAME_STEMS: Tuple[str, ...] = ("test", "tests", "spec", "specs", "conftest")


class LanguageCatalogue:
    """Immutable lookup over a set of :class:`LanguageDescriptor` records.

    The catalogue is constructed once and shared. It performs no I/O and holds no
    mutable state, so a single instance is safe to share across threads and
    worker processes.

    Args:
        descriptors: Language descriptors to index.

    Raises:
        ValueError: If two descriptors claim the same extension or filename,
            which would make classification non-deterministic.
    """

    def __init__(self, descriptors: Tuple[LanguageDescriptor, ...]) -> None:
        by_extension: Dict[str, LanguageDescriptor] = {}
        by_filename: Dict[str, LanguageDescriptor] = {}
        for descriptor in descriptors:
            for extension in descriptor.extensions:
                if extension in by_extension:
                    raise ValueError(
                        f"extension {extension!r} claimed by both "
                        f"{by_extension[extension].name!r} and {descriptor.name!r}"
                    )
                by_extension[extension] = descriptor
            for filename in descriptor.filenames:
                if filename in by_filename:
                    raise ValueError(
                        f"filename {filename!r} claimed by both "
                        f"{by_filename[filename].name!r} and {descriptor.name!r}"
                    )
                by_filename[filename] = descriptor
        self._descriptors = descriptors
        self._by_extension: Mapping[str, LanguageDescriptor] = by_extension
        self._by_filename: Mapping[str, LanguageDescriptor] = by_filename
        self._by_name: Mapping[str, LanguageDescriptor] = {
            descriptor.name: descriptor for descriptor in descriptors
        }

    @property
    def descriptors(self) -> Tuple[LanguageDescriptor, ...]:
        """All descriptors in the catalogue."""
        return self._descriptors

    def describe(self, name: str) -> Optional[LanguageDescriptor]:
        """Look up a descriptor by canonical language name.

        Args:
            name: Canonical language name.

        Returns:
            The descriptor, or ``None`` if the language is not catalogued.
        """
        return self._by_name.get(name)

    def detect_language(self, normalised_path: str) -> str:
        """Determine the language of a path.

        Args:
            normalised_path: Path produced by
                :func:`ria.domain.paths.normalise_repository_path`.

        Returns:
            Canonical language name, or :data:`UNKNOWN_LANGUAGE`.
        """
        filename = posixpath.basename(normalised_path).lower()
        by_filename = self._by_filename.get(filename)
        if by_filename is not None:
            return by_filename.name
        descriptor = self._by_extension.get(self._extension_of(filename))
        return descriptor.name if descriptor is not None else UNKNOWN_LANGUAGE

    def tier_for(self, language: str) -> LanguageTier:
        """Extraction tier available for a language.

        Args:
            language: Canonical language name.

        Returns:
            The declared tier, or :attr:`~ria.domain.enums.LanguageTier.NONE` for
            an uncatalogued language.
        """
        descriptor = self._by_name.get(language)
        return descriptor.tier if descriptor is not None else LanguageTier.NONE

    def classify(self, normalised_path: str) -> FileClassification:
        """Classify a path by its role in the repository.

        Precedence is documented in the module docstring: vendored and generated
        directories outrank test conventions, which outrank extension defaults.

        Args:
            normalised_path: Path produced by
                :func:`ria.domain.paths.normalise_repository_path`.

        Returns:
            The classification of the file.
        """
        lowered = normalised_path.lower()
        segments = lowered.split("/")
        directories = segments[:-1]
        filename = segments[-1]
        extension = self._extension_of(filename)

        if extension in _BINARY_EXTENSIONS:
            return FileClassification.BINARY
        if any(segment in _VENDORED_SEGMENTS for segment in directories):
            return FileClassification.VENDORED
        if any(segment in _GENERATED_SEGMENTS for segment in directories):
            return FileClassification.GENERATED
        if filename in _LOCK_FILENAMES:
            return FileClassification.CONFIG
        if any(marker in filename for marker in _GENERATED_MARKERS):
            return FileClassification.GENERATED
        if self._is_test(directories, filename, extension):
            return FileClassification.TEST

        descriptor = self._by_filename.get(filename) or self._by_extension.get(
            extension
        )
        if descriptor is not None:
            return descriptor.default_classification
        return FileClassification.UNKNOWN

    @staticmethod
    def _extension_of(filename: str) -> str:
        """Extract the lowercase extension of a filename, including the dot."""
        _, extension = posixpath.splitext(filename)
        return extension.lower()

    @staticmethod
    def _is_test(directories: Sequence[str], filename: str, extension: str) -> bool:
        """Whether a path matches a test convention.

        Args:
            directories: Lowercase directory segments of the path.
            filename: Lowercase basename.
            extension: Lowercase extension including the dot.
        """
        if any(segment in _TEST_SEGMENTS for segment in directories):
            return True
        stem = filename[: -len(extension)] if extension else filename
        if stem in _TEST_FILENAME_STEMS:
            return True
        if stem.startswith(_TEST_FILENAME_PREFIXES):
            return True
        return stem.endswith(_TEST_FILENAME_SUFFIXES)


#: Shared catalogue instance. Immutable and safe to share across threads.
DEFAULT_LANGUAGE_CATALOGUE = LanguageCatalogue(_LANGUAGES)
