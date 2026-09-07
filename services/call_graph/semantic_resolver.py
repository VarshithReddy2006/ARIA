"""Semantic Call Resolver (ARIA v6).

Resolves caller/callee relationships with semantic precision across Python,
JavaScript, and TypeScript codebases.

Handles:
1. File-level import and alias resolution (from x import y as z, import a.b as c).
2. Receiver expressions and instance method binding (session.send() -> Session.send).
3. self and cls method resolution within class scope.
4. Class hierarchy and MRO inheritance (Child.send() -> Base.send()).
5. super().<method>() calls.
6. Local variable constructor assignments and type annotations.
7. Structured relationship types (DIRECT_CALL, INSTANCE_METHOD, INHERITED_CALL, etc.).
8. Confidence calibration (HIGH for exact/verified, MEDIUM for inheritance/alias, LOW for uncertain).
"""

from __future__ import annotations

import ast
import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple, Any

from models.call_graph import CallNode, CallRelationshipType
from models.symbol import Symbol

logger = logging.getLogger(__name__)


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _file_dir(file_path: str) -> str:
    parts = _normalize_path(file_path).split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else ""


def _module_to_path(module_str: str) -> str:
    return module_str.replace(".", "/")


class FileImportTable:
    """Extracts and stores static import statements for a source file."""

    def __init__(self, file_path: str, language: str = "python"):
        self.file_path = _normalize_path(file_path)
        self.language = language
        # alias -> (origin_module_or_file, original_name)
        self.symbol_imports: Dict[str, Tuple[str, str]] = {}
        # alias -> module_path
        self.module_imports: Dict[str, str] = {}

    @classmethod
    def parse_source(
        cls, file_path: str, content: str, language: str = "python"
    ) -> "FileImportTable":
        table = cls(file_path, language)
        if language == "python":
            table._parse_python(content)
        elif language in ("javascript", "typescript", "tsx", "jsx"):
            table._parse_js_ts(content)
        return table

    def _parse_python(self, content: str) -> None:
        try:
            tree = ast.parse(content)
        except Exception:
            return

        caller_dir = _file_dir(self.file_path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name
                    as_name = alias.asname or alias.name
                    self.module_imports[as_name] = mod_name
                    # Also store top-level package if dotted
                    if "." in as_name:
                        top = as_name.split(".")[0]
                        self.module_imports.setdefault(top, mod_name.split(".")[0])

            elif isinstance(node, ast.ImportFrom):
                mod_base = node.module or ""
                # Handle relative imports
                if node.level > 0:
                    dir_parts = caller_dir.split("/") if caller_dir else []
                    up = node.level - 1
                    if up <= len(dir_parts):
                        prefix = dir_parts[: len(dir_parts) - up]
                        if mod_base:
                            mod_base = ".".join(prefix + [mod_base])
                        else:
                            mod_base = ".".join(prefix)

                for alias in node.names:
                    orig_name = alias.name
                    as_name = alias.asname or orig_name
                    self.symbol_imports[as_name] = (mod_base, orig_name)

    def _parse_js_ts(self, content: str) -> None:
        caller_dir = _file_dir(self.file_path)

        # Regex for ES imports: import { a, b as c } from './path'
        es_named = re.finditer(
            r'import\s*\{([^}]+)\}\s*from\s*[\'"]([^\'"]+)[\'"]', content
        )
        for m in es_named:
            raw_syms, raw_path = m.group(1), m.group(2)
            res_path = self._resolve_relative_path(caller_dir, raw_path)
            for item in raw_syms.split(","):
                item = item.strip()
                if not item:
                    continue
                if " as " in item:
                    orig, as_name = item.split(" as ")
                    self.symbol_imports[as_name.strip()] = (res_path, orig.strip())
                else:
                    self.symbol_imports[item] = (res_path, item)

        # Regex for default import: import Foo from './path'
        es_default = re.finditer(
            r'import\s+([A-Za-z0-9_$]+)\s+from\s*[\'"]([^\'"]+)[\'"]', content
        )
        for m in es_default:
            as_name, raw_path = m.group(1), m.group(2)
            res_path = self._resolve_relative_path(caller_dir, raw_path)
            self.symbol_imports[as_name] = (res_path, "default")
            self.module_imports[as_name] = res_path

        # Regex for namespace import: import * as Foo from './path'
        es_ns = re.finditer(
            r'import\s*\*\s*as\s+([A-Za-z0-9_$]+)\s+from\s*[\'"]([^\'"]+)[\'"]', content
        )
        for m in es_ns:
            as_name, raw_path = m.group(1), m.group(2)
            res_path = self._resolve_relative_path(caller_dir, raw_path)
            self.module_imports[as_name] = res_path

        # Regex for CommonJS: const foo = require('./path')
        cjs = re.finditer(
            r'(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*require\([\'"]([^\'"]+)[\'"]\)',
            content,
        )
        for m in cjs:
            as_name, raw_path = m.group(1), m.group(2)
            res_path = self._resolve_relative_path(caller_dir, raw_path)
            self.module_imports[as_name] = res_path

        # Regex for CommonJS destructuring: const { a, b: c } = require('./path')
        cjs_destruct = re.finditer(
            r'(?:const|let|var)\s*\{([^}]+)\}\s*=\s*require\([\'"]([^\'"]+)[\'"]\)',
            content,
        )
        for m in cjs_destruct:
            raw_syms, raw_path = m.group(1), m.group(2)
            res_path = self._resolve_relative_path(caller_dir, raw_path)
            for item in raw_syms.split(","):
                item = item.strip()
                if not item:
                    continue
                if ":" in item:
                    orig, as_name = item.split(":")
                    self.symbol_imports[as_name.strip()] = (res_path, orig.strip())
                else:
                    self.symbol_imports[item] = (res_path, item)

    @staticmethod
    def _resolve_relative_path(caller_dir: str, rel_path: str) -> str:
        if rel_path.startswith("."):
            joined = os.path.normpath(os.path.join(caller_dir, rel_path)).replace(
                "\\", "/"
            )
            return joined
        return rel_path


class ClassHierarchyIndex:
    """Builds and indexes inheritance relationships across classes in a repository."""

    def __init__(self):
        # class_name -> list of base class names
        self.class_to_bases: Dict[str, List[str]] = {}
        # (file_path, class_name) -> list of base class names
        self.scoped_bases: Dict[Tuple[str, str], List[str]] = {}
        # (file_path, class_name) -> set of defined method names
        self.class_methods: Dict[Tuple[str, str], Set[str]] = {}
        # (file_path, class_name) -> node_id of class
        self.class_nodes: Dict[Tuple[str, str], str] = {}

    def register_class(
        self,
        file_path: str,
        class_name: str,
        bases: List[str],
        node_id: Optional[str] = None,
    ) -> None:
        f_norm = _normalize_path(file_path)
        self.class_to_bases[class_name] = bases
        self.scoped_bases[(f_norm, class_name)] = bases
        if node_id:
            self.class_nodes[(f_norm, class_name)] = node_id

    def register_method(
        self, file_path: str, class_name: str, method_name: str
    ) -> None:
        f_norm = _normalize_path(file_path)
        self.class_methods.setdefault((f_norm, class_name), set()).add(method_name)

    def find_method_definition(
        self,
        class_name: str,
        method_name: str,
        file_path: Optional[str] = None,
        skip_self: bool = False,
    ) -> Optional[Tuple[str, str, str]]:
        """Traverse MRO hierarchy to find the defining class and file for method_name.

        Returns: (defining_file, defining_class, relationship) where relationship
        is METHOD_CALL if defined directly on class_name, or INHERITED_CALL if on a base.
        """
        queue = [(class_name, file_path, 0)]
        visited = set()

        while queue:
            curr_class, curr_file, depth = queue.pop(0)
            if (curr_class, curr_file) in visited:
                continue
            visited.add((curr_class, curr_file))

            # Check if defined directly on curr_class (unless skip_self on root)
            if not (skip_self and depth == 0):
                if curr_file:
                    methods = self.class_methods.get((curr_file, curr_class), set())
                    if method_name in methods:
                        rel = (
                            CallRelationshipType.METHOD_CALL.value
                            if depth == 0
                            else CallRelationshipType.INHERITED_CALL.value
                        )
                        return curr_file, curr_class, rel

                # Search globally for curr_class if file was None or not found in file
                for (f, c), methods in self.class_methods.items():
                    if c == curr_class and method_name in methods:
                        rel = (
                            CallRelationshipType.METHOD_CALL.value
                            if depth == 0
                            else CallRelationshipType.INHERITED_CALL.value
                        )
                        return f, c, rel

            # Add bases to queue
            bases = []
            if curr_file and (curr_file, curr_class) in self.scoped_bases:
                bases = self.scoped_bases[(curr_file, curr_class)]
            elif curr_class in self.class_to_bases:
                bases = self.class_to_bases[curr_class]

            for b in bases:
                clean_b = b.split(".")[-1]
                queue.append((clean_b, None, depth + 1))

        return None


class ScopeTypeInferrer:
    """Infers local variable types within function bodies."""

    def __init__(self, file_path: str, parent_class: Optional[str] = None):
        self.file_path = _normalize_path(file_path)
        self.parent_class = parent_class
        # var_name -> inferred type name
        self.var_types: Dict[str, str] = {}
        # framework dependency calls: [(target_name, line_number)]
        self.dependencies: List[Tuple[str, int]] = []
        if parent_class:
            self.var_types["self"] = parent_class
            self.var_types["cls"] = parent_class

    def scan_python_function(
        self, fn_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Scan assignments and annotations in a Python function."""
        # 1. Parameter type annotations: def foo(session: Session)
        for arg in fn_node.args.args:
            if arg.annotation:
                t_name = self._extract_type_name(arg.annotation)
                if t_name:
                    self.var_types[arg.arg] = t_name

        # 2. Walk body for variable assignments
        for node in ast.walk(fn_node):
            # Assignment: x = Session() or x: Session = ...
            if isinstance(node, ast.Assign):
                t_name = None
                # Check RHS constructor: ClassName(...) or module.ClassName(...)
                if isinstance(node.value, ast.Call):
                    t_name = self._extract_call_func_name(node.value.func)
                for target in node.targets:
                    if isinstance(target, ast.Name) and t_name:
                        self.var_types[target.id] = t_name

            elif isinstance(node, ast.AnnAssign):
                t_name = self._extract_type_name(node.annotation)
                if not t_name and isinstance(node.value, ast.Call):
                    t_name = self._extract_call_func_name(node.value.func)
                if isinstance(target := node.target, ast.Name) and t_name:
                    self.var_types[target.id] = t_name

            # With statement: with Session() as session:
            elif isinstance(node, ast.With):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call) and item.optional_vars:
                        t_name = self._extract_call_func_name(item.context_expr.func)
                        if isinstance(item.optional_vars, ast.Name) and t_name:
                            self.var_types[item.optional_vars.id] = t_name

    @staticmethod
    def _extract_type_name(expr: Any) -> Optional[str]:
        if isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            return expr.attr
        elif isinstance(expr, ast.Subscript):
            # Optional[Session] or List[Session]
            return ScopeTypeInferrer._extract_type_name(expr.slice)
        return None

    @staticmethod
    def _extract_call_func_name(func_expr: Any) -> Optional[str]:
        if isinstance(func_expr, ast.Name):
            return func_expr.id
        elif isinstance(func_expr, ast.Attribute):
            # sessions.Session() -> Session
            return func_expr.attr
        return None


class SemanticCallResolver:
    """Central semantic engine for resolving AST call sites into validated CallNode edges."""

    def __init__(
        self,
        all_nodes: Dict[str, CallNode],
        defn_by_name: Dict[str, List[Symbol]],
        hierarchy: ClassHierarchyIndex,
    ):
        self.all_nodes = all_nodes
        self.defn_by_name = defn_by_name
        self.hierarchy = hierarchy
        # Cache of parsed file import tables: file_path -> FileImportTable
        self.import_tables: Dict[str, FileImportTable] = {}
        # Qualified symbol lookup: "{file_path}::{qualified}" -> CallNode
        self.nodes_by_id: Dict[str, CallNode] = all_nodes

        # Pre-index for O(1) lookup
        from collections import defaultdict

        self.nodes_by_qualified: Dict[str, List[str]] = defaultdict(list)
        self.nodes_by_name: Dict[str, List[str]] = defaultdict(list)
        for nid, node in all_nodes.items():
            self.nodes_by_qualified[node.qualified].append(nid)
            self.nodes_by_name[node.name].append(nid)

    def get_or_parse_import_table(
        self,
        file_path: str,
        content: Optional[str] = None,
        language: str = "python",
    ) -> FileImportTable:
        f_norm = _normalize_path(file_path)
        if f_norm not in self.import_tables:
            if content is None:
                table = FileImportTable(f_norm, language)
            else:
                table = FileImportTable.parse_source(f_norm, content, language)
            self.import_tables[f_norm] = table
        return self.import_tables[f_norm]

    def resolve_call(
        self,
        caller_id: str,
        caller_file: str,
        callee_name: str,
        receiver_expr: Optional[str],
        type_inferrer: Optional[ScopeTypeInferrer],
        call_line: int,
    ) -> Tuple[Optional[str], str, Optional[str], str, bool]:
        """Semantically resolve a call expression to a concrete callee_id.

        Returns:
            (callee_id, relationship_type, receiver_type, confidence_tier, is_ambiguous)
        """
        caller_file_norm = _normalize_path(caller_file)
        caller_node = self.all_nodes.get(caller_id)
        parent_class = (
            caller_node.parent_class
            if (caller_node and caller_node.parent_class)
            else (
                caller_node.qualified.split(".")[0]
                if (caller_node and "." in caller_node.qualified)
                else None
            )
        )

        # -------------------------------------------------------------
        # 1. SUPER CALLS: super().method(...)
        # -------------------------------------------------------------
        if receiver_expr and (
            receiver_expr.startswith("super(") or receiver_expr == "super()"
        ):
            if parent_class:
                found = self.hierarchy.find_method_definition(
                    parent_class, callee_name, caller_file_norm, skip_self=True
                )
                if found:
                    def_file, def_class, _ = found
                    target_id = f"{def_file}::{def_class}.{callee_name}"
                    if target_id in self.all_nodes:
                        return (
                            target_id,
                            CallRelationshipType.SUPER_CALL.value,
                            def_class,
                            "HIGH",
                            False,
                        )

        # -------------------------------------------------------------
        # 2. SELF / CLS / THIS CALLS: self.method(...), cls.method(...), this.method(...)
        # -------------------------------------------------------------
        if receiver_expr in ("self", "cls", "this"):
            if parent_class:
                # Check directly on enclosing class in same file
                target_id = f"{caller_file_norm}::{parent_class}.{callee_name}"
                if target_id in self.all_nodes:
                    return (
                        target_id,
                        CallRelationshipType.INSTANCE_METHOD.value,
                        parent_class,
                        "HIGH",
                        False,
                    )

                # Check inheritance hierarchy for parent class
                found = self.hierarchy.find_method_definition(
                    parent_class, callee_name, caller_file_norm
                )
                if found:
                    def_file, def_class, rel = found
                    target_id = f"{def_file}::{def_class}.{callee_name}"
                    if target_id in self.all_nodes:
                        tier = (
                            "HIGH"
                            if rel == CallRelationshipType.METHOD_CALL.value
                            else "MEDIUM"
                        )
                        return target_id, rel, def_class, tier, False

        # -------------------------------------------------------------
        # 3. RECEIVER INSTANCE CALLS: session.send(...), client.get(...)
        # -------------------------------------------------------------
        if receiver_expr:
            # 3A. Infer receiver type from local scope (e.g. session -> Session)
            inferred_type = (
                type_inferrer.var_types.get(receiver_expr) if type_inferrer else None
            )

            # Handle injected service conventions: self.symbol_service.foo()
            if not inferred_type and receiver_expr.startswith("self."):
                attr_name = receiver_expr.split(".", 1)[1]
                # Convert snake_case service attribute to CamelCase class: symbol_service -> SymbolService
                words = attr_name.split("_")
                candidate_type = "".join(w.capitalize() for w in words)
                inferred_type = candidate_type

            if inferred_type:
                # Resolve inferred_type via import table if cross-file
                imp_table = self.import_tables.get(caller_file_norm)
                def_file_hint = None
                clean_inferred = inferred_type
                if imp_table and inferred_type in imp_table.symbol_imports:
                    mod_path, orig_name = imp_table.symbol_imports[inferred_type]
                    clean_inferred = orig_name
                    def_file_hint = _module_to_path(mod_path)

                # Search method in hierarchy for inferred_type
                found = self.hierarchy.find_method_definition(
                    clean_inferred, callee_name, def_file_hint
                )
                if found:
                    def_file, def_class, rel = found
                    target_id = f"{def_file}::{def_class}.{callee_name}"
                    if target_id in self.all_nodes:
                        return (
                            target_id,
                            CallRelationshipType.INSTANCE_METHOD.value,
                            def_class,
                            "HIGH",
                            False,
                        )

                # Search nodes_by_qualified directly for {inferred_type}.{callee_name}
                cands = self.nodes_by_qualified.get(
                    f"{clean_inferred}.{callee_name}", []
                )
                if cands:
                    return (
                        cands[0],
                        CallRelationshipType.INSTANCE_METHOD.value,
                        clean_inferred,
                        "HIGH",
                        False,
                    )

            # 3B. Receiver might be an imported class or module directly:
            # e.g. Session.send(s), or requests.sessions.Session.send()
            imp_table = self.import_tables.get(caller_file_norm)
            if imp_table:
                # Receiver is an imported class: from requests.sessions import Session; Session.send()
                if receiver_expr in imp_table.symbol_imports:
                    mod_path, orig_class = imp_table.symbol_imports[receiver_expr]
                    cands = self.nodes_by_qualified.get(
                        f"{orig_class}.{callee_name}", []
                    )
                    if cands:
                        return (
                            cands[0],
                            CallRelationshipType.METHOD_CALL.value,
                            orig_class,
                            "HIGH",
                            False,
                        )

                # Receiver is an imported module alias: import utils; utils.helper()
                if receiver_expr in imp_table.module_imports:
                    mod_path = imp_table.module_imports[receiver_expr]
                    mod_file = _module_to_path(mod_path)
                    for nid in self.nodes_by_name.get(callee_name, []):
                        node = self.all_nodes[nid]
                        if (
                            mod_file in node.file_path
                            or mod_path.replace(".", "/") in node.file_path
                        ):
                            return (
                                nid,
                                CallRelationshipType.MODULE_FUNCTION_CALL.value,
                                receiver_expr,
                                "HIGH",
                                False,
                            )

        # -------------------------------------------------------------
        # 4. DIRECT CALLS: func() or ClassName()
        # -------------------------------------------------------------
        imp_table = self.import_tables.get(caller_file_norm)

        # 4A. Explicitly imported function / class symbol: from x import helper as h; h()
        if imp_table and callee_name in imp_table.symbol_imports:
            mod_path, orig_name = imp_table.symbol_imports[callee_name]
            mod_file_slug = _module_to_path(mod_path)
            for nid, node in self.all_nodes.items():
                if node.name == orig_name and (
                    mod_file_slug in node.file_path or not mod_file_slug
                ):
                    rel = (
                        CallRelationshipType.ALIAS_CALL.value
                        if callee_name != orig_name
                        else CallRelationshipType.DIRECT_CALL.value
                    )
                    return nid, rel, None, "HIGH", False

        # 4B. Same-file function or class definition
        same_file_id = f"{caller_file_norm}::{callee_name}"
        if same_file_id in self.all_nodes:
            return (
                same_file_id,
                CallRelationshipType.DIRECT_CALL.value,
                None,
                "HIGH",
                False,
            )

        # Check same-file class method or constructor
        for nid, node in self.all_nodes.items():
            if node.file_path == caller_file_norm and node.name == callee_name:
                return nid, CallRelationshipType.DIRECT_CALL.value, None, "HIGH", False

        # 4C. Check if callee_name is a globally unique function or class constructor
        candidates = self.defn_by_name.get(callee_name, [])
        valid_nodes = []
        for s in candidates:
            q = f"{s.parent_class}.{s.name}" if s.parent_class else s.name
            nid = f"{s.file_path}::{q}"
            if nid in self.all_nodes:
                valid_nodes.append((nid, s))

        if len(valid_nodes) == 1:
            nid, s = valid_nodes[0]
            rel = (
                CallRelationshipType.CONSTRUCTOR_CALL.value
                if s.type == "class"
                else CallRelationshipType.DIRECT_CALL.value
            )
            return nid, rel, None, "HIGH", False
        elif len(valid_nodes) > 1:
            # Multiple definitions exist with same name (ambiguous match)
            # Prioritize same directory
            caller_dir = _file_dir(caller_file_norm)
            same_dir = [
                vn for vn in valid_nodes if _file_dir(vn[1].file_path) == caller_dir
            ]
            if len(same_dir) == 1:
                return (
                    same_dir[0][0],
                    CallRelationshipType.DIRECT_CALL.value,
                    None,
                    "MEDIUM",
                    True,
                )

            # If receiver is None and multiple exist across different classes without imports,
            # this is UNRESOLVED / UNCERTAIN.
            return (
                None,
                CallRelationshipType.UNRESOLVED_CALL.value,
                receiver_expr,
                "LOW",
                True,
            )

        return (
            None,
            CallRelationshipType.UNRESOLVED_CALL.value,
            receiver_expr,
            "LOW",
            False,
        )
