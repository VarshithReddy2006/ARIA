"""Symbol Intelligence Service — PH2-002.

Extracts, persists, and queries symbol-level metadata from repository source
files using the Tree-sitter AST.  Symbols are the foundation for:

  - PH2-003 PR Intelligence  (changed functions → callers → risk)
  - Dead Code Detection       (symbols with zero references)
  - Architecture Drift        (unexpected new public symbols in stable modules)

Design:
  - Reuses TreeSitterService's parser cache to avoid duplicate grammar loading.
  - Performs its OWN AST walk so it can capture node.start_point (line numbers),
    which TreeSitterService.parse_file() does not expose.
  - Persistence mirrors ArchitectureService: JSON in data/symbols/, versioned
    with _schema_version, stale indices auto-discarded on load.
  - No new databases.  No Graphology.  No Neo4j.  No LangGraph.

Supported symbol types:
  Python      → function, class, method
  JavaScript  → function, class, method
  TypeScript  → function, class, method, interface, enum
  TSX         → function, class, method, interface, enum
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from models.symbol import Symbol, SymbolIndex
from services.tree_sitter_service import TreeSitterService, _LANGUAGE_REGISTRY
from storage.snapshot_store import SnapshotStore
from core.cache import AnalysisCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_SYMBOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "symbols",
)

# Increment when the schema or extraction logic changes.
# Older persisted indices are automatically discarded.
_SCHEMA_VERSION = 1


class SymbolService:
    """Extracts, persists, and queries symbol-level intelligence.

    This service is stateless between calls; each build() writes an index
    that all query methods read from.
    """

    @property
    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    @classmethod
    def get_schema_version(cls) -> int:
        return _SCHEMA_VERSION

    def __init__(
        self,
        symbols_dir: str = _SYMBOLS_DIR,
        snapshot_store: Optional[SnapshotStore] = None,
        analysis_cache: Optional[AnalysisCache] = None,
    ) -> None:
        """Initialise the service.

        Args:
            symbols_dir: Directory where symbol JSON indices are saved.
                         Defaults to data/symbols/ relative to project root.
            snapshot_store: Shared snapshot store instance.
            analysis_cache: Shared analysis cache instance.
        """
        self.symbols_dir = symbols_dir
        os.makedirs(self.symbols_dir, exist_ok=True)

        if snapshot_store is None:
            if symbols_dir != _SYMBOLS_DIR:
                parent_dir = os.path.dirname(symbols_dir)
                dir_name = os.path.basename(symbols_dir)
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore(
                    base_dir=parent_dir, key_map={"symbols": dir_name}
                )
            else:
                from storage.snapshot_store import JsonSnapshotStore

                self.snapshot_store = JsonSnapshotStore()
        else:
            self.snapshot_store = snapshot_store

        self.analysis_cache = analysis_cache or AnalysisCache()

        # Reuse TreeSitterService's lazy-loading parser cache
        self._ts = TreeSitterService()

    # ------------------------------------------------------------------
    # Public API — Build
    # ------------------------------------------------------------------

    def build(
        self,
        repo_name: str,
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Extract symbols from a repository and persist the index.

        Provides backward compatibility by delegating to build_full.
        """
        return self.build_full(repo_name, repo_path=repo_path, files=files)

    def build_full(
        self,
        repo_name: str,
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Extract all symbols from scratch and persist the index."""
        if repo_path is None and files is None:
            raise ValueError("Provide either repo_path or files.")

        file_list = files if files is not None else self._walk_repo(repo_path)

        symbols: List[Symbol] = []
        files_indexed = 0
        for f in file_list:
            path = f.get("path", "")
            content = f.get("content", "")
            if not path or not content:
                continue
            file_syms = self._extract_file_symbols(path, content)
            if file_syms:
                symbols.extend(file_syms)
                files_indexed += 1

        self._save(repo_name, symbols)
        logger.info(
            "Full symbol index built for %s — %d symbols from %d files",
            repo_name,
            len(symbols),
            files_indexed,
        )
        return {
            "status": "success",
            "repo": repo_name,
            "symbol_count": len(symbols),
            "files_indexed": files_indexed,
        }

    def build_partial(
        self,
        repo_name: str,
        changed_files: Set[str],
        repo_path: Optional[str] = None,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Incrementally update the symbol index using changed files list."""
        old_index = self.load(repo_name)
        if old_index is None:
            logger.info(
                "No existing symbol index found for %s, running full build.", repo_name
            )
            return self.build_full(repo_name, repo_path=repo_path, files=files)

        if repo_path is None and files is None:
            raise ValueError("Provide either repo_path or files.")

        file_list = files if files is not None else self._walk_repo(repo_path)

        # 1. Filter out symbols belonging to modified or deleted files
        retained_symbols = [
            sym for sym in old_index.symbols if sym.file_path not in changed_files
        ]

        # 2. Extract new symbols from added or modified files
        new_symbols: List[Symbol] = []
        files_indexed = 0
        for f in file_list:
            path = f.get("path", "")
            content = f.get("content", "")
            if not path or not content:
                continue
            # Only parse files that have actually changed
            if path in changed_files:
                file_syms = self._extract_file_symbols(path, content)
                if file_syms:
                    new_symbols.extend(file_syms)
                    files_indexed += 1

        # 3. Merge and save
        merged_symbols = retained_symbols + new_symbols
        self._save(repo_name, merged_symbols)
        logger.info(
            "Incremental symbol index built for %s — %d retained, %d new from %d changed files",
            repo_name,
            len(retained_symbols),
            len(new_symbols),
            files_indexed,
        )
        return {
            "status": "success",
            "repo": repo_name,
            "symbol_count": len(merged_symbols),
            "files_indexed": files_indexed,
        }

    # ------------------------------------------------------------------
    # Public API — Query
    # ------------------------------------------------------------------

    def index_exists(self, repo_name: str) -> bool:
        """Return True if a symbol index exists for *repo_name*."""
        return self.snapshot_store.exists(repo_name, "symbols")

    def load(self, repo_name: str) -> Optional[SymbolIndex]:
        """Load a persisted symbol index.

        Returns:
            A SymbolIndex Pydantic model, or None if not found / stale.
        """
        cached = self.analysis_cache.get(repo_name, "symbols", _SCHEMA_VERSION)
        if cached is not None:
            return cached

        data = self.snapshot_store.load(repo_name, "symbols")
        if data is None:
            return None

        stored_version = data.get("_schema_version", 0)
        if stored_version < _SCHEMA_VERSION:
            logger.warning(
                "Discarding stale symbol index for %s (schema v%d < current v%d)",
                repo_name,
                stored_version,
                _SCHEMA_VERSION,
            )
            return None

        try:
            filtered = {k: v for k, v in data.items() if not k.startswith("_")}
            index = SymbolIndex(**filtered)
            self.analysis_cache.set(repo_name, "symbols", index, _SCHEMA_VERSION)
            return index
        except Exception as exc:
            logger.error(
                "Failed to deserialise symbol index for %s: %s", repo_name, exc
            )
            return None

    def get_file_symbols(
        self, repo_name: str, file_path: str
    ) -> Optional[List[Symbol]]:
        """Return all symbols defined in *file_path*.

        Args:
            repo_name: Repository identifier.
            file_path: Relative file path (uses forward slashes for matching).

        Returns:
            List of Symbol objects, or None if no index exists for the repo.
        """
        index = self.load(repo_name)
        if index is None:
            return None
        norm = file_path.replace("\\", "/").lower()
        return index.file_symbol_map.get(norm, [])

    def get_definition(self, repo_name: str, symbol_name: str) -> Optional[Symbol]:
        """Return the first symbol matching *symbol_name*.

        Priority order: class → function → method → interface → enum.
        Returns None if the symbol is not found or no index exists.
        """
        index = self.load(repo_name)
        if index is None:
            return None
        _priority = {
            "class": 0,
            "function": 1,
            "method": 2,
            "interface": 3,
            "enum": 4,
            "variable": 5,
        }
        matches = index.name_symbol_map.get(symbol_name.lower(), [])
        if not matches:
            return None
        # Prioritize exact case match if present
        exact_case = [s for s in matches if s.name == symbol_name]
        candidates = exact_case if exact_case else matches
        return sorted(candidates, key=lambda s: _priority.get(s.type, 99))[0]

    def get_references(
        self, repo_name: str, symbol_name: str
    ) -> Optional[List[Symbol]]:
        """Return all symbols whose name matches *symbol_name*.

        Returns:
            List of Symbol objects (may be empty), or None if no index exists.
        """
        index = self.load(repo_name)
        if index is None:
            return None
        matches = index.name_symbol_map.get(symbol_name.lower(), [])
        return [s for s in matches if s.name == symbol_name] or matches

    # ------------------------------------------------------------------
    # Symbol Extraction — per-file entry point
    # ------------------------------------------------------------------

    def _extract_file_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """Parse one file with Tree-sitter and return Symbol objects.

        Uses TreeSitterService._get_parser() to reuse the cached parser, then
        walks the raw AST to capture node.start_point[0] + 1 as line_number.
        This avoids modifying TreeSitterService while providing accurate line
        numbers not available via parse_file().
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in _LANGUAGE_REGISTRY:
            return []

        language_name, loader = _LANGUAGE_REGISTRY[ext]
        parser = self._ts._get_parser(language_name, loader)
        if parser is None:
            return []

        try:
            tree = parser.parse(content.encode("utf-8", errors="replace"))
        except Exception as exc:
            logger.warning("Symbol extraction parse error for %s: %s", file_path, exc)
            return []

        root = tree.root_node

        if language_name == "python":
            return self._walk_python(root, file_path, "python")
        else:
            # javascript, typescript, tsx
            return self._walk_js_ts(root, file_path, language_name)

    # ------------------------------------------------------------------
    # Python AST walker
    # ------------------------------------------------------------------

    def _walk_python(self, root, file_path: str, lang: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        for node in root.children:
            nt = node.type
            if nt == "function_definition":
                sym = self._python_fn(node, file_path, lang)
                if sym:
                    symbols.append(sym)
            elif nt == "class_definition":
                symbols.extend(self._python_class(node, file_path, lang))
            elif nt == "decorated_definition":
                # @decorator\ndef foo() / class Foo
                for child in node.children:
                    if child.type == "function_definition":
                        sym = self._python_fn(child, file_path, lang)
                        if sym:
                            symbols.append(sym)
                    elif child.type == "class_definition":
                        symbols.extend(self._python_class(child, file_path, lang))
        return symbols

    def _python_fn(
        self,
        node,
        file_path: str,
        lang: str,
        parent_class: Optional[str] = None,
    ) -> Optional[Symbol]:
        name = self._node_name(node)
        if not name:
            return None
        return Symbol(
            name=name,
            type="method" if parent_class else "function",
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            language=lang,
            parent_class=parent_class,
        )

    def _python_class(self, node, file_path: str, lang: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        class_name = ""

        # First pass: capture class name
        for child in node.children:
            if child.type == "identifier" and not class_name:
                class_name = child.text.decode("utf-8", errors="replace")

        if not class_name:
            return symbols

        symbols.append(
            Symbol(
                name=class_name,
                type="class",
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                language=lang,
            )
        )

        # Second pass: walk block for methods
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        sym = self._python_fn(
                            stmt, file_path, lang, parent_class=class_name
                        )
                        if sym:
                            symbols.append(sym)
                    elif stmt.type == "decorated_definition":
                        for sub in stmt.children:
                            if sub.type == "function_definition":
                                sym = self._python_fn(
                                    sub, file_path, lang, parent_class=class_name
                                )
                                if sym:
                                    symbols.append(sym)

        return symbols

    # ------------------------------------------------------------------
    # JavaScript / TypeScript AST walker
    # ------------------------------------------------------------------

    def _walk_js_ts(self, root, file_path: str, lang: str) -> List[Symbol]:
        symbols: List[Symbol] = []

        for node in root.children:
            nt = node.type

            if nt == "function_declaration":
                sym = self._js_fn(node, file_path, lang)
                if sym:
                    symbols.append(sym)

            elif nt in ("class_declaration", "class"):
                symbols.extend(self._js_class(node, file_path, lang))

            elif nt == "lexical_declaration":
                # const fn = (x) => ...
                for child in node.children:
                    if child.type == "variable_declarator":
                        sym = self._js_arrow(child, file_path, lang)
                        if sym:
                            symbols.append(sym)

            elif nt == "export_statement":
                symbols.extend(self._js_export(node, file_path, lang))

            # TypeScript-specific top-level declarations
            elif nt == "interface_declaration":
                sym = self._ts_interface(node, file_path, lang)
                if sym:
                    symbols.append(sym)

            elif nt == "enum_declaration":
                sym = self._ts_enum(node, file_path, lang)
                if sym:
                    symbols.append(sym)

        return symbols

    def _js_export(self, export_node, file_path: str, lang: str) -> List[Symbol]:
        """Handle export_statement wrapping function/class/interface/enum."""
        symbols: List[Symbol] = []
        for child in export_node.children:
            ct = child.type
            if ct == "function_declaration":
                sym = self._js_fn(child, file_path, lang)
                if sym:
                    symbols.append(sym)
            elif ct in ("class_declaration", "class"):
                symbols.extend(self._js_class(child, file_path, lang))
            elif ct == "lexical_declaration":
                for sub in child.children:
                    if sub.type == "variable_declarator":
                        sym = self._js_arrow(sub, file_path, lang)
                        if sym:
                            symbols.append(sym)
            elif ct == "interface_declaration":
                sym = self._ts_interface(child, file_path, lang)
                if sym:
                    symbols.append(sym)
            elif ct == "enum_declaration":
                sym = self._ts_enum(child, file_path, lang)
                if sym:
                    symbols.append(sym)
        return symbols

    def _js_fn(
        self,
        node,
        file_path: str,
        lang: str,
        parent_class: Optional[str] = None,
    ) -> Optional[Symbol]:
        name = self._node_name(node)
        if not name:
            return None
        return Symbol(
            name=name,
            type="method" if parent_class else "function",
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            language=lang,
            parent_class=parent_class,
        )

    def _js_arrow(self, declarator_node, file_path: str, lang: str) -> Optional[Symbol]:
        """Handle `const fn = (x) => ...` variable declarator nodes."""
        name = ""
        has_arrow = False
        for child in declarator_node.children:
            if child.type == "identifier" and not name:
                name = child.text.decode("utf-8", errors="replace")
            elif child.type == "arrow_function":
                has_arrow = True
        if name and has_arrow:
            return Symbol(
                name=name,
                type="function",
                file_path=file_path,
                line_number=declarator_node.start_point[0] + 1,
                language=lang,
            )
        return None

    def _js_class(self, node, file_path: str, lang: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        class_name = ""

        for child in node.children:
            if child.type in ("identifier", "type_identifier") and not class_name:
                class_name = child.text.decode("utf-8", errors="replace")

        if not class_name:
            return symbols

        symbols.append(
            Symbol(
                name=class_name,
                type="class",
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                language=lang,
            )
        )

        # Walk class_body for methods
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    if member.type == "method_definition":
                        name = self._node_name(member)
                        if name:
                            symbols.append(
                                Symbol(
                                    name=name,
                                    type="method",
                                    file_path=file_path,
                                    line_number=member.start_point[0] + 1,
                                    language=lang,
                                    parent_class=class_name,
                                )
                            )

        return symbols

    def _ts_interface(self, node, file_path: str, lang: str) -> Optional[Symbol]:
        name = self._node_name(node)
        if not name:
            return None
        return Symbol(
            name=name,
            type="interface",
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            language=lang,
        )

    def _ts_enum(self, node, file_path: str, lang: str) -> Optional[Symbol]:
        name = self._node_name(node)
        if not name:
            return None
        return Symbol(
            name=name,
            type="enum",
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            language=lang,
        )

    # ------------------------------------------------------------------
    # Generic AST helper
    # ------------------------------------------------------------------

    @staticmethod
    def _node_name(node) -> str:
        """Return the first identifier or type_identifier child text."""
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                return child.text.decode("utf-8", errors="replace")
        return ""

    # ------------------------------------------------------------------
    # Disk walk helper (mirrors ArchitectureService._walk_repo_paths)
    # ------------------------------------------------------------------

    _IGNORED_DIRS = {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "venv",
        "__pycache__",
        ".venv",
        ".tox",
        "coverage",
    }

    def _walk_repo(self, repo_path: str) -> List[Dict[str, str]]:
        """Walk *repo_path* and return [{path, content}] for supported files."""
        file_list = []
        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in self._IGNORED_DIRS]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in _LANGUAGE_REGISTRY:
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, repo_path).replace(os.sep, "/")
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    file_list.append({"path": rel, "content": content})
                except Exception as exc:
                    logger.debug("Could not read %s: %s", full, exc)
        return file_list

    # ------------------------------------------------------------------
    # Persistence (mirrors ArchitectureService pattern exactly)
    # ------------------------------------------------------------------

    def _index_path(self, repo_name: str) -> str:
        return self.snapshot_store._get_path(repo_name, "symbols")

    def _save(self, repo_name: str, symbols: List[Symbol]) -> None:
        payload = {
            "repo": repo_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol_count": len(symbols),
            "symbols": [s.model_dump() for s in symbols],
            "_schema_version": _SCHEMA_VERSION,
            "_built_at": int(time.time()),
        }
        self.snapshot_store.save(repo_name, "symbols", payload)

        try:
            index_obj = SymbolIndex(
                repo=repo_name,
                generated_at=payload["generated_at"],
                symbol_count=len(symbols),
                symbols=symbols,
            )
            self.analysis_cache.set(repo_name, "symbols", index_obj, _SCHEMA_VERSION)
        except Exception as exc:
            logger.error("Failed to update cache in SymbolService._save: %s", exc)

    def _load_raw(self, repo_name: str) -> Optional[Dict[str, Any]]:
        return self.snapshot_store.load(repo_name, "symbols")
