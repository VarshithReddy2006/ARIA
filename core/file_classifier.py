"""File classification and language scoring utility.

Provides deterministic categorization of repository files:
  - category: "production" | "test" | "docs" | "example" | "config" | "generated"
  - language: normalized language identifier (e.g. "Python", "TypeScript", "JavaScript", etc.)
  - source_priority: ranking weight for RAG retrieval and chunking
  - weight: language stack detection weight factor
"""

import os
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Categories and weights
# ---------------------------------------------------------------------------
CATEGORY_PRODUCTION = "production"
CATEGORY_TEST = "test"
CATEGORY_DOCS = "docs"
CATEGORY_EXAMPLE = "example"
CATEGORY_CONFIG = "config"
CATEGORY_GENERATED = "generated"

# RAG source priority (0.0 to 1.0)
CATEGORY_SOURCE_PRIORITY = {
    CATEGORY_PRODUCTION: 1.0,
    CATEGORY_DOCS: 0.6,
    CATEGORY_EXAMPLE: 0.4,
    CATEGORY_TEST: 0.3,
    CATEGORY_CONFIG: 0.2,
    CATEGORY_GENERATED: 0.0,
}

# Language stack detection weights
CATEGORY_STACK_WEIGHT = {
    CATEGORY_PRODUCTION: 10.0,
    CATEGORY_CONFIG: 2.0,
    CATEGORY_EXAMPLE: 2.0,
    CATEGORY_TEST: 1.0,
    CATEGORY_DOCS: 0.1,
    CATEGORY_GENERATED: 0.0,
}

# ---------------------------------------------------------------------------
# Path & pattern rules
# ---------------------------------------------------------------------------
_GENERATED_DIR_PARTS = frozenset(
    {
        "dist",
        "build",
        "out",
        "coverage",
        "node_modules",
        "vendor",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".cache",
        ".git",
        ".tox",
        "target",
        "bin",
        "obj",
        ".next",
        ".turbo",
        ".output",
    }
)

_GENERATED_EXTENSIONS = frozenset(
    {
        ".min.js",
        ".min.css",
        ".map",
        ".pyc",
        ".pyo",
        ".pyd",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".bin",
        ".snap",
        ".lock",
    }
)

_GENERATED_FILENAMES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
        "cargo.lock",
        "gemfile.lock",
        "composer.lock",
    }
)

_TEST_DIR_PARTS = frozenset(
    {
        "tests",
        "test",
        "__tests__",
        "spec",
        "specs",
        "fixtures",
        "mocks",
        "test_utils",
    }
)

_EXAMPLE_DIR_PARTS = frozenset(
    {
        "docs_src",
        "examples",
        "example",
        "samples",
        "sample",
        "demo",
        "demos",
        "tutorials",
        "tutorial",
        "cookbook",
        "benchmarks",
        "benchmark",
        "showcase",
    }
)

_DOCS_DIR_PARTS = frozenset(
    {
        "docs",
        "doc",
        "documentation",
        "site",
        "wiki",
        "mkdocs",
    }
)

_CONFIG_FILENAMES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "tsconfig.json",
        "cargo.toml",
        "go.mod",
        "go.sum",
        "gemfile",
        "composer.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "docker-compose.prod.yml",
        "makefile",
        "cmakelists.txt",
        ".env.example",
        ".flake8",
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.js",
        ".prettierrc",
    }
)

_DOCS_FILENAMES_PREFIX = (
    "readme",
    "contributing",
    "changelog",
    "license",
    "architecture",
    "code_of_conduct",
    "authors",
    "security",
)


# Extension to standard Language name
_EXT_TO_LANGUAGE = {
    ".py": "Python",
    ".pyi": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".c": "C",
    ".h": "C",
    ".scala": "Scala",
    ".dart": "Dart",
    ".lua": "Lua",
    ".r": "R",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    ".less": "CSS",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".rst": "Documentation",
    ".json": "JSON",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
}


def classify_file(file_path: str) -> Dict[str, Any]:
    """Deterministically classify a repository file into architectural category and language.

    Args:
        file_path: Relative path to the file.

    Returns:
        Dictionary with category, language, source_priority, weight, and entry_point_candidate flag.
    """
    normalized = file_path.replace("\\", "/").strip().lstrip("/")
    lower_path = normalized.lower()
    parts = lower_path.split("/")
    filename = parts[-1]
    name_no_ext, ext = os.path.splitext(filename)

    # 1. Generated / Build artifacts / Excluded
    if any(p in _GENERATED_DIR_PARTS for p in parts[:-1]):
        return _make_classification(CATEGORY_GENERATED, file_path, ext)

    if filename in _GENERATED_FILENAMES:
        return _make_classification(CATEGORY_GENERATED, file_path, ext)

    for gen_ext in _GENERATED_EXTENSIONS:
        if lower_path.endswith(gen_ext):
            return _make_classification(CATEGORY_GENERATED, file_path, ext)

    if filename.endswith("_pb2.py") or filename.endswith("_pb2_grpc.py"):
        return _make_classification(CATEGORY_GENERATED, file_path, ext)

    # 2. Examples / Tutorials / Demos (e.g. docs_src)
    if any(p in _EXAMPLE_DIR_PARTS for p in parts[:-1]):
        return _make_classification(CATEGORY_EXAMPLE, file_path, ext)

    # 3. Tests
    if any(p in _TEST_DIR_PARTS for p in parts[:-1]):
        return _make_classification(CATEGORY_TEST, file_path, ext)

    if (
        filename.startswith("test_")
        or filename.endswith("_test.py")
        or filename.endswith(".test.ts")
        or filename.endswith(".test.js")
        or filename.endswith(".test.tsx")
        or filename.endswith(".test.jsx")
        or filename.endswith(".spec.ts")
        or filename.endswith(".spec.js")
        or filename.endswith(".spec.tsx")
        or filename.endswith(".spec.jsx")
        or filename.endswith("_spec.rb")
    ):
        return _make_classification(CATEGORY_TEST, file_path, ext)

    # 4. Configuration & Manifests
    if filename in _CONFIG_FILENAMES or filename.startswith("requirements"):
        return _make_classification(CATEGORY_CONFIG, file_path, ext)

    # 5. Documentation
    if any(p in _DOCS_DIR_PARTS for p in parts[:-1]):
        return _make_classification(CATEGORY_DOCS, file_path, ext)

    if ext in (".md", ".markdown", ".rst", ".adoc", ".txt"):
        return _make_classification(CATEGORY_DOCS, file_path, ext)

    if not ext and any(
        name_no_ext.startswith(prefix) for prefix in _DOCS_FILENAMES_PREFIX
    ):
        return _make_classification(CATEGORY_DOCS, file_path, ext)

    # 6. Production source code
    return _make_classification(CATEGORY_PRODUCTION, file_path, ext)


def _make_classification(category: str, file_path: str, ext: str) -> Dict[str, Any]:
    language = _EXT_TO_LANGUAGE.get(ext.lower(), "Text")

    # Specific manifest language overrides
    fn = os.path.basename(file_path).lower()
    if fn in ("pyproject.toml", "setup.py", "setup.cfg") or fn.startswith(
        "requirements"
    ):
        language = "Python"
    elif fn in ("package.json", "tsconfig.json"):
        language = "TypeScript" if fn.startswith("tsconfig") else "JavaScript"
    elif fn in ("cargo.toml", "cargo.lock"):
        language = "Rust"
    elif fn in ("go.mod", "go.sum"):
        language = "Go"

    return {
        "path": file_path,
        "category": category,
        "language": language,
        "source_priority": CATEGORY_SOURCE_PRIORITY.get(category, 0.5),
        "weight": CATEGORY_STACK_WEIGHT.get(category, 1.0),
        "is_production": category == CATEGORY_PRODUCTION,
    }
