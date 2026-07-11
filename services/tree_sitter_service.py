"""Tree-Sitter Parsing Service.



Parses repository source files using Tree-Sitter grammars to extract structural

metadata: imports, classes (with base classes and methods), and top-level

functions.



Supported languages (Phase 1): Python, JavaScript, TypeScript, JSX, TSX.

The registry pattern allows new languages to be added with minimal changes.

"""

import logging

import os

from typing import Any, Dict, List, Optional, Tuple


import threading


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------

# Language registry

# ---------------------------------------------------------------------------

# Each entry maps an extension to (language_name, loader_callable).

# loader_callable() must return a tree-sitter Language object.

# New languages can be added here without touching parsing logic.


def _load_python_language():

    # tree_sitter-python returns a pointer-like int

    import tree_sitter_python as tspython

    return tspython.language()


def _load_javascript_language():

    # tree_sitter-javascript returns a pointer-like int

    import tree_sitter_javascript as tsjs

    return tsjs.language()


def _load_typescript_language():

    # tree_sitter-typescript returns a pointer-like int

    import tree_sitter_typescript as tsts

    return tsts.language_typescript()


def _load_tsx_language():

    # tree_sitter-typescript returns a pointer-like int

    import tree_sitter_typescript as tsts

    return tsts.language_tsx()


# Extension → (canonical language name, loader)

_LANGUAGE_REGISTRY: Dict[str, Tuple[str, Any]] = {
    ".py": ("python", _load_python_language),
    ".js": ("javascript", _load_javascript_language),
    ".jsx": ("javascript", _load_javascript_language),
    ".ts": ("typescript", _load_typescript_language),
    ".tsx": ("tsx", _load_tsx_language),
}


class TreeSitterService:
    """Parses source files with Tree-Sitter and extracts structural metadata.



    The service lazily initialises parsers per language and caches them for

    the lifetime of the instance, so repeated calls on the same language are

    cheap.

    """

    def __init__(self) -> None:

        # Thread-local storage for parsers: each thread gets its own Parser cache

        self._local = threading.local()

    # ------------------------------------------------------------------

    # Public API

    # ------------------------------------------------------------------

    def is_supported(self, file_path: str) -> bool:
        """Returns True if the file extension is supported by this service."""

        ext = os.path.splitext(file_path)[1].lower()

        return ext in _LANGUAGE_REGISTRY

    def parse_file(self, file_path: str, content: str) -> Optional[Dict[str, Any]]:
        """Parse a single source file and return structural metadata.



        Args:

            file_path: Relative or absolute path to the source file.

            content: UTF-8 text content of the file.



        Returns:

            A dictionary with keys:

                file_path   – as provided

                language    – canonical language name

                imports     – list of imported module/package strings

                classes     – list of {class_name, base_classes, methods}

                functions   – list of {function_name, parameters}

            Returns None if the file extension is not supported.

        """

        ext = os.path.splitext(file_path)[1].lower()

        if ext not in _LANGUAGE_REGISTRY:
            return None

        language_name, loader = _LANGUAGE_REGISTRY[ext]

        parser = self._get_parser(language_name, loader)

        if parser is None:
            return None

        try:
            tree = parser.parse(content.encode("utf-8", errors="replace"))

        except Exception as exc:
            logger.warning("Tree-Sitter parse error for %s: %s", file_path, exc)

            return None

        root = tree.root_node

        if language_name == "python":
            imports, classes, functions = self._extract_python(root)

        else:
            # javascript / typescript / tsx share the same extraction logic

            imports, classes, functions = self._extract_js_ts(root, content)

        # Collect exports for JS/TS family

        exports: List[str] = []

        if language_name in ("javascript", "typescript", "tsx"):
            exports = self._extract_exports(root)

        result: Dict[str, Any] = {
            "file_path": file_path,
            "language": language_name,
            "imports": imports,
            "classes": classes,
            "functions": functions,
        }

        if exports:
            result["exports"] = exports

        return result

    def parse_repository(
        self,
        repo_path: str,
        files: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Parse all supported files in a repository.



        Args:

            repo_path: Root path of the repository (used for relative path

                       normalisation when *files* is None).

            files: Optional pre-extracted list of {path, content} dicts (the

                   same format produced by GitHubService.extract_source_files).

                   When provided, disk reads are skipped.



        Returns:

            List of parsed file metadata dicts (see parse_file).

        """

        if files is not None:
            return self._parse_file_list(files)

        return self._parse_from_disk(repo_path)

    # ------------------------------------------------------------------

    # Internal helpers – parser management

    # ------------------------------------------------------------------

    def _get_parser(self, language_name: str, loader) -> Optional[Any]:
        """Return a cached Parser for the given language, creating one if needed."""

        if not hasattr(self._local, "parsers"):
            self._local.parsers = {}

        if language_name in self._local.parsers:
            return self._local.parsers[language_name]

        try:
            from tree_sitter import Parser, Language

            language_ptr = loader()

            parser = Parser()

            # tree-sitter 0.21.x API: Language constructor requires both pointer and name.

            # Grammar packages return a pointer-like int via *.language()*.

            lang_obj = Language(language_ptr, language_name)

            parser.set_language(lang_obj)

            self._local.parsers[language_name] = parser

            return parser

        except Exception as exc:
            logger.error(
                "Failed to initialise Tree-Sitter parser for %s: %s", language_name, exc
            )

            return None

    # ------------------------------------------------------------------

    # Internal helpers – disk / list scanning

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

    def _parse_from_disk(self, repo_path: str) -> List[Dict[str, Any]]:

        results = []

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

                except Exception as exc:
                    logger.debug("Could not read %s: %s", full, exc)

                    continue

                parsed = self.parse_file(rel, content)

                if parsed:
                    results.append(parsed)

        return results

    def _parse_file_list(self, files: List[Dict[str, str]]) -> List[Dict[str, Any]]:

        results = []

        for f in files:
            path = f.get("path", "")

            content = f.get("content", "")

            parsed = self.parse_file(path, content)

            if parsed:
                results.append(parsed)

        return results

    # ------------------------------------------------------------------

    # Python extraction

    # ------------------------------------------------------------------

    def _extract_python(self, root) -> Tuple[List[str], List[Dict], List[Dict]]:

        imports: List[str] = []

        classes: List[Dict] = []

        functions: List[Dict] = []

        for node in root.children:
            ntype = node.type

            if ntype == "import_statement":
                # e.g. import os, import os.path

                for child in node.children:
                    if child.type == "dotted_name":
                        imports.append(child.text.decode("utf-8", errors="replace"))

                    elif child.type == "aliased_import":
                        # import foo as bar → grab dotted_name child

                        for sub in child.children:
                            if sub.type == "dotted_name":
                                imports.append(
                                    sub.text.decode("utf-8", errors="replace")
                                )

                                break

            elif ntype == "import_from_statement":
                # e.g. from services.foo import Bar

                module = ""

                for child in node.children:
                    if child.type == "dotted_name":
                        module = child.text.decode("utf-8", errors="replace")

                        break

                if module:
                    imports.append(module)

            elif ntype == "class_definition":
                classes.append(self._extract_python_class(node))

            elif ntype == "function_definition":
                functions.append(self._extract_python_function(node))

            elif ntype == "decorated_definition":
                # @decorator\ndef foo / class Foo

                for child in node.children:
                    if child.type == "function_definition":
                        functions.append(self._extract_python_function(child))

                    elif child.type == "class_definition":
                        classes.append(self._extract_python_class(child))

        return imports, classes, functions

    def _extract_python_class(self, node) -> Dict:

        class_name = ""

        base_classes: List[str] = []

        methods: List[str] = []

        for child in node.children:
            if child.type == "identifier" and not class_name:
                class_name = child.text.decode("utf-8", errors="replace")

            elif child.type == "argument_list":
                # base classes sit as identifier / dotted_name children

                for arg in child.children:
                    if arg.type in ("identifier", "dotted_name"):
                        base_classes.append(arg.text.decode("utf-8", errors="replace"))

            elif child.type == "block":
                # Walk block to find method definitions

                for stmt in child.children:
                    if stmt.type == "function_definition":
                        methods.append(self._get_identifier(stmt))

                    elif stmt.type == "decorated_definition":
                        for sub in stmt.children:
                            if sub.type == "function_definition":
                                methods.append(self._get_identifier(sub))

        return {
            "class_name": class_name,
            "base_classes": base_classes,
            "methods": methods,
        }

    def _extract_python_function(self, node) -> Dict:

        name = self._get_identifier(node)

        params: List[str] = []

        for child in node.children:
            if child.type == "parameters":
                for p in child.children:
                    if p.type in (
                        "identifier",
                        "typed_parameter",
                        "typed_default_parameter",
                        "default_parameter",
                        "list_splat_pattern",
                        "dictionary_splat_pattern",
                    ):
                        # Grab the identifier inside typed params, or the node text for simple ones

                        if p.type == "identifier":
                            params.append(p.text.decode("utf-8", errors="replace"))

                        else:
                            ident = self._get_identifier(p)

                            if ident:
                                params.append(ident)

        return {"function_name": name, "parameters": params}

    # ------------------------------------------------------------------

    # JavaScript / TypeScript extraction

    # ------------------------------------------------------------------

    def _extract_js_ts(
        self, root, content: str
    ) -> Tuple[List[str], List[Dict], List[Dict]]:

        imports: List[str] = []

        classes: List[Dict] = []

        functions: List[Dict] = []

        for node in root.children:
            ntype = node.type

            if ntype == "import_statement":
                src = self._js_import_source(node)

                if src:
                    imports.append(src)

            elif ntype == "lexical_declaration":
                # const foo = require('bar')  or  const fn = (x) => ...

                for child in node.children:
                    if child.type == "variable_declarator":
                        self._handle_js_var_declarator(child, imports, functions)

            elif ntype in ("class_declaration", "class"):
                classes.append(self._extract_js_class(node))

            elif ntype == "function_declaration":
                functions.append(self._extract_js_function(node))

            elif ntype == "export_statement":
                # export function foo() {} / export class Foo {}

                for child in node.children:
                    if child.type == "function_declaration":
                        functions.append(self._extract_js_function(child))

                    elif child.type in ("class_declaration", "class"):
                        classes.append(self._extract_js_class(child))

                    elif child.type == "lexical_declaration":
                        for sub in child.children:
                            if sub.type == "variable_declarator":
                                self._handle_js_var_declarator(sub, imports, functions)

        return imports, classes, functions

    def _js_import_source(self, node) -> Optional[str]:
        """Extract module specifier string from an import_statement node."""

        for child in node.children:
            if child.type == "string":
                raw = child.text.decode("utf-8", errors="replace")

                return raw.strip("'\"` ")

        return None

    def _handle_js_var_declarator(
        self, node, imports: List[str], functions: List[Dict]
    ):
        """Handle  const x = require('y')  and  const fn = (x) => ...  patterns."""

        name = ""

        for child in node.children:
            if child.type == "identifier" and not name:
                name = child.text.decode("utf-8", errors="replace")

            elif child.type == "call_expression":
                fn_node = child.children[0] if child.children else None

                if (
                    fn_node
                    and fn_node.type == "identifier"
                    and fn_node.text == b"require"
                ):
                    # extract string argument

                    for arg_child in child.children:
                        if arg_child.type == "arguments":
                            for a in arg_child.children:
                                if a.type == "string":
                                    raw = a.text.decode("utf-8", errors="replace")

                                    imports.append(raw.strip("'\"` "))

            elif child.type == "arrow_function":
                params = self._extract_js_arrow_params(child)

                functions.append({"function_name": name, "parameters": params})

    def _extract_js_arrow_params(self, node) -> List[str]:

        params: List[str] = []

        for child in node.children:
            if child.type == "formal_parameters":
                for p in child.children:
                    if p.type == "identifier":
                        params.append(p.text.decode("utf-8", errors="replace"))

            elif child.type == "identifier":
                # single-param arrow: x => ...

                params.append(child.text.decode("utf-8", errors="replace"))

                break

        return params

    def _extract_js_class(self, node) -> Dict:

        class_name = ""

        base_classes: List[str] = []

        methods: List[str] = []

        for child in node.children:
            if child.type == "identifier" and not class_name:
                class_name = child.text.decode("utf-8", errors="replace")

            elif child.type == "type_identifier" and not class_name:
                class_name = child.text.decode("utf-8", errors="replace")

            elif child.type in ("class_heritage",):
                for h in child.children:
                    if h.type in ("identifier", "type_identifier"):
                        base_classes.append(h.text.decode("utf-8", errors="replace"))

            elif child.type == "class_body":
                for member in child.children:
                    if member.type in ("method_definition", "function_declaration"):
                        methods.append(self._get_identifier(member))

                    elif member.type == "public_field_definition":
                        # potential arrow-function field – just record the field name

                        ident = self._get_identifier(member)

                        if ident:
                            methods.append(ident)

        return {
            "class_name": class_name,
            "base_classes": base_classes,
            "methods": methods,
        }

    def _extract_js_function(self, node) -> Dict:

        name = self._get_identifier(node)

        params: List[str] = []

        for child in node.children:
            if child.type == "formal_parameters":
                for p in child.children:
                    if p.type == "identifier":
                        params.append(p.text.decode("utf-8", errors="replace"))

                    elif p.type in (
                        "required_parameter",
                        "optional_parameter",
                        "rest_pattern",
                        "assignment_pattern",
                    ):
                        ident = self._get_identifier(p)

                        if ident:
                            params.append(ident)

        return {"function_name": name, "parameters": params}

    def _extract_exports(self, root) -> List[str]:
        """Collect exported names from export_statement nodes."""

        exports: List[str] = []

        for node in root.children:
            if node.type != "export_statement":
                continue

            for child in node.children:
                if child.type == "export_clause":
                    for spec in child.children:
                        if spec.type == "export_specifier":
                            ident = self._get_identifier(spec)

                            if ident:
                                exports.append(ident)

                elif child.type == "identifier":
                    exports.append(child.text.decode("utf-8", errors="replace"))

                elif child.type in ("class_declaration", "function_declaration"):
                    ident = self._get_identifier(child)

                    if ident:
                        exports.append(ident)

        return exports

    # ------------------------------------------------------------------

    # Generic helpers

    # ------------------------------------------------------------------

    @staticmethod
    def _get_identifier(node) -> str:
        """Return the first identifier or type_identifier text inside *node*."""

        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return child.text.decode("utf-8", errors="replace")

        return ""
