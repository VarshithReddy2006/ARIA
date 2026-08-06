# Milestone 3 — Parser Layer

**Status:** complete
**Implements:** SDD section 3 (L2 Parser Layer), tree-sitter integration, language plugin architecture, extractor interfaces, AST generation, query engine, parse caching, incremental parsing, and the parser & capability registries.
**Package:** `ria/`
**Tests:** 870 measured passed total in 1.9s.

---

## 1. Scope

| Item | Where |
|---|---|
| Domain Models | `PluginIdentity`, `ExtractorDescriptor`, `LanguagePluginDescriptor`, `ParseCacheEntry` |
| Enums | `IngestionStage.PARSE` (pipeline order 8) |
| Ports | `ParserPort`, `SyntaxExtractorPort`, `LanguagePluginPort`, `ParserRegistryPort`, `ParseCacheStore`, `CapabilityRegistryPort` in `ria/ports/parser.py` |
| Tree-sitter Adapter | `TreeSitterAdapter` in `ria/infrastructure/parser/tree_sitter_adapter.py` |
| Language Plugins | `DefaultLanguagePlugin` in `ria/application/language_plugin.py` |
| Extractors | `PythonSyntaxExtractor`, `JsTsSyntaxExtractor` in `ria/infrastructure/parser/extractors/` |
| Parser Registry | `ParserRegistry`, `build_default_parser_registry` in `ria/application/parser_registry.py` & `ria/container.py` |
| Capability Registry | `CapabilityRegistry` in `ria/application/capability_registry.py` |
| AST Generator | `AstGenerator` in `ria/application/ast_generator.py` |
| Parse Cache | `SqliteParseCacheStore` in `ria/infrastructure/storage/sqlite/parse_cache_store.py` & `0003_parser_layer.sql` |
| Incremental Parser | `IncrementalParser` in `ria/application/incremental_parser.py` |
| Parser Orchestrator | `ParserService` in `ria/application/parser_service.py` |
| Ingestion Pipeline Seam | `IngestionService` (stage `PARSE`) in `ria/application/ingestion_service.py` |
| Composition Root | `Container` in `ria/container.py` |

Nothing from Milestone 4 (Semantic Layer / Symbol Index) or later is present.

---

## 2. Subsystems

### 2.1 Parser Domain Models & Enums — `ria/domain/models/` & `ria/domain/enums.py`
- `PluginIdentity`: Identifies language name and plugin version.
- `ExtractorDescriptor`: Extractor component identity and declared capabilities.
- `LanguagePluginDescriptor`: Complete plugin declaration, extension mapping, fingerprinting, and minimum capability validation (`PARSE`, `PRODUCE_AST`).
- `ParseCacheEntry`: Domain representation of a cached result with authoritative `ParseCacheKey` and UTC timestamp.
- `IngestionStage.PARSE`: Positioned at order 8 between `DETECT_CHANGES` (7) and `PERSIST` (9).

### 2.2 Parser Ports — `ria/ports/parser.py`
Defines 6 hexagonal `typing.Protocol` ports with zero third-party dependencies:
- `ParserPort`
- `SyntaxExtractorPort`
- `LanguagePluginPort`
- `ParserRegistryPort`
- `ParseCacheStore`
- `CapabilityRegistryPort`

### 2.3 Tree-sitter Adapter — `ria/infrastructure/parser/tree_sitter_adapter.py`
Converts tree-sitter C/Python AST nodes into domain `SyntaxNode` and `SyntaxTree` objects.
Features thread-local parser caching, error and missing node flagging, zero third-party leaks to higher layers.

### 2.4 Extractors — `ria/infrastructure/parser/extractors/`
- `PythonSyntaxExtractor`: Extracts functions, methods, classes, imports, decorators/annotations, docstrings, visibility, and comments.
- `JsTsSyntaxExtractor`: Extracts functions, methods, classes, interfaces, imports, exports, and comments.

### 2.5 Parser & Capability Registries — `ria/application/parser_registry.py` & `ria/application/capability_registry.py`
Thread-safe registries managing registered language plugins, file extensions, and capabilities.

### 2.6 AST Generator — `ria/application/ast_generator.py`
Produces deterministic `SyntaxTree` objects with identical structural digests for identical input bytes.

### 2.7 Parse Cache Store — `ria/infrastructure/storage/sqlite/parse_cache_store.py` & `0003_parser_layer.sql`
Durable content-addressed SQLite cache store for `ParseResult` objects, keyed by `ParseCacheKey.digest()`.

### 2.8 Incremental Parser & Service — `ria/application/incremental_parser.py` & `ria/application/parser_service.py`
Consumes `ChangeSet.paths_requiring_reparse()` to reparse only changed files, reusing cached results for unchanged and renamed files.

---

## 3. Verification

```bash
# Full test suite
pytest tests/ria/integration/test_architecture_rules.py tests/ria/unit tests/ria/integration -q   # 870 passed in 1.9s

# Linter and formatting
ruff check ria tests/ria       # All checks passed!
ruff format --check .          # All files clean!
```
