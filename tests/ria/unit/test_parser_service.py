"""Comprehensive unit tests for Milestone 3 Parser Layer components.

Covers:
- DefaultLanguagePlugin (Step 4)
- ParserRegistry (Step 5)
- Python & JS/TS Extractors (Step 6)
- AstGenerator (Step 7)
- IncrementalParser (Step 8 & 9)
- CapabilityRegistry (Step 10)
- ParserService (Step 11)
"""

from __future__ import annotations

from typing import Sequence

import pytest

from ria.application.ast_generator import AstGenerator
from ria.application.capability_registry import CapabilityRegistry
from ria.application.incremental_parser import IncrementalParser
from ria.application.parser_registry import ParserRegistry
from ria.application.parser_service import ParserService
from ria.container import build_default_parser_registry
from ria.domain.enums import (
    DeclarationKind,
    FileClassification,
    LanguageTier,
    ParseStatus,
    ParserCapability,
)
from ria.domain.identity import CommitSha, ContentHash, RepositoryId
from ria.domain.models.change_set import ChangeSet, RenamedPath
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parser_identity import ParseCacheKey, ParserFingerprint
from ria.infrastructure.parser.extractors.js_ts_extractor import JsTsSyntaxExtractor
from ria.infrastructure.parser.extractors.python_extractor import PythonSyntaxExtractor
from ria.infrastructure.parser.tree_sitter_adapter import TreeSitterAdapter

REPO_ID = RepositoryId("repo-123")
COMMIT_SHA = CommitSha("a" * 40)
CONTENT_HASH_1 = ContentHash.of_bytes(
    b"def greet(name: str) -> str:\n    return f'Hello {name}'\n"
)
CONTENT_HASH_2 = ContentHash.of_bytes(b"function add(a, b) {\n  return a + b;\n}\n")


class InMemoryBlobStore:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, data: bytes) -> str:
        h = ContentHash.of_bytes(data).value
        self.blobs[h] = data
        return h

    def get(self, content_hash: str | ContentHash) -> bytes:
        key = (
            content_hash.value if hasattr(content_hash, "value") else str(content_hash)
        )
        return self.blobs[key]

    def has(self, content_hash: str | ContentHash) -> bool:
        key = (
            content_hash.value if hasattr(content_hash, "value") else str(content_hash)
        )
        return key in self.blobs

    def missing(self, hashes: Sequence[str]) -> Sequence[str]:
        return tuple(h for h in hashes if h not in self.blobs)


class InMemoryParseCacheStore:
    def __init__(self) -> None:
        self.store: dict[str, ParseCacheEntry] = {}

    def get(self, key: ParseCacheKey) -> ParseCacheEntry | None:
        return self.store.get(key.digest())

    def put(self, entry: ParseCacheEntry) -> None:
        self.store[entry.key.digest()] = entry

    def invalidate_by_reuse_key(self, reuse_key: str) -> int:
        keys_to_del = [k for k, v in self.store.items() if v.key.reuse_key == reuse_key]
        for k in keys_to_del:
            del self.store[k]
        return len(keys_to_del)

    def invalidate_by_fingerprint(self, fingerprint: ParserFingerprint) -> int:
        keys_to_del = [
            k for k, v in self.store.items() if v.key.fingerprint == fingerprint
        ]
        for k in keys_to_del:
            del self.store[k]
        return len(keys_to_del)

    def clear(self) -> None:
        self.store.clear()


@pytest.fixture
def parser_adapter() -> TreeSitterAdapter:
    return TreeSitterAdapter()


@pytest.fixture
def parser_registry(parser_adapter: TreeSitterAdapter) -> ParserRegistry:
    return build_default_parser_registry(parser_adapter)


@pytest.fixture
def cache_store() -> InMemoryParseCacheStore:
    return InMemoryParseCacheStore()


@pytest.fixture
def blob_store() -> InMemoryBlobStore:
    bs = InMemoryBlobStore()
    bs.put(b"def greet(name: str) -> str:\n    return f'Hello {name}'\n")
    bs.put(b"function add(a, b) {\n  return a + b;\n}\n")
    return bs


class TestParserRegistry:
    def test_duplicate_registration_raises(
        self, parser_adapter: TreeSitterAdapter
    ) -> None:
        registry = ParserRegistry()
        plugin = build_default_parser_registry(parser_adapter).get_plugin("python")
        registry.register_plugin(plugin)

        with pytest.raises(ValueError, match="already registered"):
            registry.register_plugin(plugin)

    def test_extension_lookup(self, parser_registry: ParserRegistry) -> None:
        plugin = parser_registry.get_plugin_for_extension(".py")
        assert plugin is not None
        assert plugin.descriptor.language == "python"

        ts_plugin = parser_registry.get_plugin_for_extension(".ts")
        assert ts_plugin is not None
        assert ts_plugin.descriptor.language == "typescript"


class TestExtractors:
    def test_python_extractor(self, parser_adapter: TreeSitterAdapter) -> None:
        code = b'# Sample python file\nimport os\n\ndef my_func(x: int) -> int:\n    """Docstring."""\n    return x + 1\n'
        tree = parser_adapter.parse_bytes(
            code, language="python", content_hash="sha256:123"
        )

        extractor = PythonSyntaxExtractor()
        extracted = extractor.extract(tree, code)

        assert len(extracted.imports) == 1
        assert extracted.imports[0].module_text == "os"
        assert len(extracted.declarations) == 1
        assert extracted.declarations[0].name == "my_func"
        assert extracted.declarations[0].kind == DeclarationKind.FUNCTION
        assert extracted.declarations[0].documentation is not None
        assert extracted.declarations[0].documentation.text == "Docstring."
        assert len(extracted.comments) == 1

    def test_js_ts_extractor(self, parser_adapter: TreeSitterAdapter) -> None:
        code = b"// JS sample\nimport { sum } from './math';\n\nexport function calc(a, b) {\n  return sum(a, b);\n}\n"
        tree = parser_adapter.parse_bytes(
            code, language="javascript", content_hash="sha256:123"
        )

        extractor = JsTsSyntaxExtractor()
        extracted = extractor.extract(tree, code)

        assert len(extracted.imports) == 1
        assert extracted.imports[0].module_text == "./math"
        assert len(extracted.exports) == 1
        assert len(extracted.declarations) == 1
        assert extracted.declarations[0].name == "calc"
        assert extracted.declarations[0].is_exported


class TestAstGenerator:
    def test_generate_ast_determinism(self, parser_adapter: TreeSitterAdapter) -> None:
        gen = AstGenerator(parser_adapter)
        code = b"def test_fn(): pass\n"
        tree1 = gen.generate_ast(code, language="python", content_hash="sha256:abc")
        tree2 = gen.generate_ast(code, language="python", content_hash="sha256:abc")

        assert tree1.structural_digest() == tree2.structural_digest()


class TestCapabilityRegistry:
    def test_capability_queries(self, parser_registry: ParserRegistry) -> None:
        cap_reg = CapabilityRegistry(parser_registry)

        py_caps = cap_reg.capabilities_for_language("python")
        assert ParserCapability.EXTRACT_FUNCTIONS in py_caps

        langs_with_fn = cap_reg.languages_with_capability(
            ParserCapability.EXTRACT_FUNCTIONS
        )
        assert "python" in langs_with_fn
        assert "javascript" in langs_with_fn

        langs_with_class = cap_reg.languages_with_declaration_kind(
            DeclarationKind.CLASS
        )
        assert "python" in langs_with_class

        assert cap_reg.max_tier_for_language("python") == LanguageTier.TIER_A


class TestIncrementalParser:
    def test_incremental_parse_with_cache_reuse(
        self,
        parser_registry: ParserRegistry,
        cache_store: InMemoryParseCacheStore,
        blob_store: InMemoryBlobStore,
    ) -> None:
        inc_parser = IncrementalParser(
            registry=parser_registry,
            cache_store=cache_store,
            blob_store=blob_store,
        )

        unit1 = FileUnit(
            repository_id=REPO_ID,
            commit_sha=COMMIT_SHA,
            path="src/main.py",
            content_hash=CONTENT_HASH_1,
            blob_sha="blob1",
            language="python",
            classification=FileClassification.SOURCE,
        )
        unit2 = FileUnit(
            repository_id=REPO_ID,
            commit_sha=COMMIT_SHA,
            path="src/utils.js",
            content_hash=CONTENT_HASH_2,
            blob_sha="blob2",
            language="javascript",
            classification=FileClassification.SOURCE,
        )

        # 1st run: Cold build (both files parsed, zero cache hits)
        results1, summary1 = inc_parser.parse_commit_units(
            [unit1, unit2], change_set=None
        )

        assert summary1.reparsed_units == 2
        assert summary1.cached_units == 0
        assert len(cache_store.store) == 2

        # 2nd run: Incremental run over ChangeSet with zero changed files -> 100% cache hits
        change_set = ChangeSet(head_sha=COMMIT_SHA.value, base_sha="b" * 40)
        results2, summary2 = inc_parser.parse_commit_units(
            [unit1, unit2], change_set=change_set
        )

        assert summary2.reparsed_units == 0
        assert summary2.cached_units == 2
        assert summary2.cache_hit_ratio == 1.0
        assert results2["src/main.py"].from_cache is True

    def test_rename_reuses_parse_artifact(
        self,
        parser_registry: ParserRegistry,
        cache_store: InMemoryParseCacheStore,
        blob_store: InMemoryBlobStore,
    ) -> None:
        inc_parser = IncrementalParser(
            registry=parser_registry,
            cache_store=cache_store,
            blob_store=blob_store,
        )

        unit1 = FileUnit(
            repository_id=REPO_ID,
            commit_sha=COMMIT_SHA,
            path="src/old_name.py",
            content_hash=CONTENT_HASH_1,
            blob_sha="blob1",
            language="python",
            classification=FileClassification.SOURCE,
        )

        # Cold build
        _, summary1 = inc_parser.parse_commit_units([unit1])
        assert summary1.reparsed_units == 1

        # Renamed unit
        renamed_unit = FileUnit(
            repository_id=REPO_ID,
            commit_sha=COMMIT_SHA,
            path="src/new_name.py",
            content_hash=CONTENT_HASH_1,
            blob_sha="blob1",
            language="python",
            classification=FileClassification.SOURCE,
        )

        rename_info = RenamedPath(
            previous_path="src/old_name.py",
            current_path="src/new_name.py",
            content_hash=CONTENT_HASH_1.value,
        )
        change_set = ChangeSet(
            head_sha=COMMIT_SHA.value,
            base_sha="b" * 40,
            renamed=(rename_info,),
        )

        results2, summary2 = inc_parser.parse_commit_units(
            [renamed_unit], change_set=change_set
        )
        assert summary2.reparsed_units == 0
        assert summary2.cached_units == 1
        assert "src/new_name.py" in results2
        assert results2["src/new_name.py"].from_cache is True


class TestParserService:
    def test_parse_commit_updates_units_and_coverage(
        self,
        parser_registry: ParserRegistry,
        cache_store: InMemoryParseCacheStore,
        blob_store: InMemoryBlobStore,
    ) -> None:
        svc = ParserService(
            cache_store=cache_store,
            blob_store=blob_store,
            registry=parser_registry,
        )

        unit1 = FileUnit(
            repository_id=REPO_ID,
            commit_sha=COMMIT_SHA,
            path="src/main.py",
            content_hash=CONTENT_HASH_1,
            blob_sha="blob1",
            language="python",
            classification=FileClassification.SOURCE,
        )

        updated_units, coverage, results, summary = svc.parse_commit([unit1])

        assert len(updated_units) == 1
        assert updated_units[0].parse_status == ParseStatus.PARSED
        assert coverage.files_parsed == 1
        assert coverage.symbols_total == 1
        assert len(coverage.by_language) == 1
        assert coverage.by_language[0].language == "python"
        assert coverage.by_language[0].files_parsed == 1
