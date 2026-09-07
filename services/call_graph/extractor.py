"""Call Graph Extractor.

Responsible for parsing source files using Tree-sitter, extracting call sites with
receiver expressions, building function scope maps, and delegating to
SemanticCallResolver for precise type and inheritance binding.
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Dict, List, Optional, Tuple

from models.call_graph import CallNode, CallRelationshipType
from models.symbol import Symbol
from services.call_graph.semantic_resolver import (
    ClassHierarchyIndex,
    ScopeTypeInferrer,
    SemanticCallResolver,
)
from services.tree_sitter_service import TreeSitterService, _LANGUAGE_REGISTRY

logger = logging.getLogger(__name__)


def _node_id(file_path: str, qualified: str) -> str:
    """Build a globally unique node ID."""
    clean_p = file_path.replace("\\", "/").lstrip("./")
    return f"{clean_p}::{qualified}"


def _qualified(symbol: Symbol) -> str:
    """Build the dot-qualified name from a Symbol."""
    if symbol.parent_class:
        return f"{symbol.parent_class}.{symbol.name}"
    return symbol.name


def _file_dir(file_path: str) -> str:
    """Return the directory portion of a normalised path."""
    return "/".join(file_path.replace("\\", "/").split("/")[:-1])


class CallGraphExtractor:
    """Extracts function call edges from AST nodes using Tree-sitter and SemanticCallResolver."""

    def __init__(self, tree_sitter_service: Optional[TreeSitterService] = None) -> None:
        self._ts = tree_sitter_service or TreeSitterService()

    def extract_call_edges(
        self,
        file_path: str,
        content: str,
        defn_by_name: Dict[str, List[Symbol]],
        all_nodes: Dict[str, CallNode],
        resolver: Optional[SemanticCallResolver] = None,
        hierarchy: Optional[ClassHierarchyIndex] = None,
    ) -> List[Tuple[str, str, int, bool, str, Optional[str], Optional[str], str]]:
        """Walk the AST and extract call edges for all functions in *file_path*.

        Returns list of:
            (caller_id, callee_id, call_line, ambiguous, relationship, receiver_expr, receiver_type, confidence)
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
            logger.debug("Call extraction parse error for %s: %s", file_path, exc)
            return []

        # Ensure we have a SemanticCallResolver
        if resolver is None:
            h = hierarchy or ClassHierarchyIndex()
            resolver = SemanticCallResolver(all_nodes, defn_by_name, h)

        # Parse and register import table for caller file
        resolver.get_or_parse_import_table(file_path, content, language_name)

        # Build scope map: (start_byte, end_byte, caller_node_id)
        scopes = self.build_scope_map(
            tree.root_node, file_path, all_nodes, language_name
        )

        # Build local type inferrers per scope for Python
        inferrers_by_node: Dict[str, ScopeTypeInferrer] = {}
        if language_name == "python":
            inferrers_by_node = self._build_python_type_inferrers(
                file_path, content, all_nodes
            )

        # Extract all call expressions: (callee_name, receiver_expr, call_line, call_byte)
        call_sites = self.find_call_sites(tree.root_node, language_name)

        edges: List[
            Tuple[str, str, int, bool, str, Optional[str], Optional[str], str]
        ] = []

        for call_name, receiver_expr, call_line, call_byte in call_sites:
            caller_id = self.find_enclosing_scope(call_byte, scopes)
            if caller_id is None:
                continue

            inferrer = inferrers_by_node.get(caller_id)

            callee_id, rel, rec_type, conf, amb = resolver.resolve_call(
                caller_id=caller_id,
                caller_file=file_path,
                callee_name=call_name,
                receiver_expr=receiver_expr,
                type_inferrer=inferrer,
                call_line=call_line,
            )

            if callee_id is None:
                # Fallback to legacy resolve if semantic resolver could not find candidate
                callee_id, amb = self.resolve_callee(
                    call_name, caller_id, file_path, defn_by_name, all_nodes
                )
                if callee_id is None:
                    continue
                rel = CallRelationshipType.DIRECT_CALL.value
                conf = "MEDIUM" if not amb else "LOW"

            if caller_id == callee_id:
                edges.append(
                    (
                        caller_id,
                        callee_id,
                        call_line,
                        False,
                        CallRelationshipType.DIRECT_CALL.value,
                        None,
                        None,
                        "HIGH",
                    )
                )
            else:
                edges.append(
                    (
                        caller_id,
                        callee_id,
                        call_line,
                        amb,
                        rel,
                        receiver_expr,
                        rec_type,
                        conf,
                    )
                )

        # Resolve framework dependencies (e.g. FastAPI Depends / Security)
        for caller_id, inferrer in inferrers_by_node.items():
            for dep_name, dep_line in inferrer.dependencies:
                callee_id, rel, rec_type, conf, amb = resolver.resolve_call(
                    caller_id=caller_id,
                    caller_file=file_path,
                    callee_name=dep_name,
                    receiver_expr=None,
                    type_inferrer=inferrer,
                    call_line=dep_line,
                )
                if callee_id:
                    edges.append(
                        (
                            caller_id,
                            callee_id,
                            dep_line,
                            amb,
                            CallRelationshipType.DECORATED_HANDLER.value,
                            None,
                            None,
                            conf,
                        )
                    )

        return edges

    def _build_python_type_inferrers(
        self,
        file_path: str,
        content: str,
        all_nodes: Dict[str, CallNode],
    ) -> Dict[str, ScopeTypeInferrer]:
        inferrers: Dict[str, ScopeTypeInferrer] = {}
        try:
            tree = ast.parse(content)
        except Exception:
            return inferrers

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.current_class: Optional[str] = None
                self.module_vars: Dict[str, str] = {}

            def visit_Assign(self, node: ast.Assign):
                if self.current_class is None and isinstance(node.value, ast.Call):
                    fn_name = ScopeTypeInferrer._extract_call_func_name(node.value.func)
                    if fn_name:
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                self.module_vars[target.id] = fn_name
                self.generic_visit(node)

            def visit_AnnAssign(self, node: ast.AnnAssign):
                if self.current_class is None and isinstance(node.value, ast.Call):
                    fn_name = ScopeTypeInferrer._extract_call_func_name(node.value.func)
                    if fn_name and isinstance(node.target, ast.Name):
                        self.module_vars[node.target.id] = fn_name
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef):
                prev = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self._handle_fn(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self._handle_fn(node)
                self.generic_visit(node)

            def _handle_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
                q = (
                    f"{self.current_class}.{node.name}"
                    if self.current_class
                    else node.name
                )
                nid = _node_id(file_path, q)
                inferrer = ScopeTypeInferrer(file_path, self.current_class)
                inferrer.scan_python_function(node)

                # Scan parameter dependencies (FastAPI Depends / Security)
                for arg in node.args.args:
                    if arg.annotation and isinstance(arg.annotation, ast.Subscript):
                        sl = arg.annotation.slice
                        elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
                        t_name = (
                            ScopeTypeInferrer._extract_type_name(elts[0])
                            if elts
                            else None
                        )
                        for elem in elts[1:]:
                            if isinstance(elem, ast.Call):
                                fn_name = ScopeTypeInferrer._extract_call_func_name(
                                    elem.func
                                )
                                if fn_name in ("Depends", "Security"):
                                    if elem.args:
                                        dep_var = ScopeTypeInferrer._extract_type_name(
                                            elem.args[0]
                                        )
                                        if dep_var:
                                            resolved_dep = self.module_vars.get(
                                                dep_var, dep_var
                                            )
                                            inferrer.dependencies.append(
                                                (
                                                    resolved_dep,
                                                    getattr(
                                                        elem, "lineno", node.lineno
                                                    ),
                                                )
                                            )
                                    elif t_name:
                                        inferrer.dependencies.append(
                                            (
                                                t_name,
                                                getattr(elem, "lineno", node.lineno),
                                            )
                                        )

                for default in node.args.defaults:
                    if isinstance(default, ast.Call):
                        fn_name = ScopeTypeInferrer._extract_call_func_name(
                            default.func
                        )
                        if fn_name in ("Depends", "Security"):
                            if default.args:
                                dep_var = ScopeTypeInferrer._extract_type_name(
                                    default.args[0]
                                )
                                if dep_var:
                                    resolved_dep = self.module_vars.get(
                                        dep_var, dep_var
                                    )
                                    inferrer.dependencies.append(
                                        (
                                            resolved_dep,
                                            getattr(default, "lineno", node.lineno),
                                        )
                                    )

                inferrers[nid] = inferrer

        Visitor().visit(tree)
        return inferrers

    def build_scope_map(
        self,
        root,
        file_path: str,
        all_nodes: Dict[str, CallNode],
        language_name: str,
    ) -> List[Tuple[int, int, str]]:
        """Build a list of (start_byte, end_byte, node_id) for all tracked functions."""
        scopes: List[Tuple[int, int, str]] = []

        def walk(node, parent_class: Optional[str] = None):
            nt = node.type

            if language_name == "python":
                if nt == "class_definition":
                    class_name = self.get_first_identifier(node)
                    for child in node.children:
                        walk(child, parent_class=class_name)
                    return
                if nt in ("function_definition", "decorated_definition"):
                    actual = node
                    if nt == "decorated_definition":
                        actual = next(
                            (
                                c
                                for c in node.children
                                if c.type == "function_definition"
                            ),
                            None,
                        )
                    if actual is None:
                        return
                    fn_name = self.get_first_identifier(actual)
                    if fn_name:
                        q = f"{parent_class}.{fn_name}" if parent_class else fn_name
                        nid = _node_id(file_path, q)
                        if nid in all_nodes:
                            scopes.append((actual.start_byte, actual.end_byte, nid))
                    for child in actual.children:
                        walk(child, parent_class=parent_class)
                    return

            else:  # JS/TS
                if nt in ("class_declaration", "class"):
                    class_name = self.get_first_identifier(node)
                    for child in node.children:
                        walk(child, parent_class=class_name)
                    return
                if nt == "method_definition":
                    fn_name = self.get_first_identifier(node)
                    if fn_name and parent_class:
                        q = f"{parent_class}.{fn_name}"
                        nid = _node_id(file_path, q)
                        if nid in all_nodes:
                            scopes.append((node.start_byte, node.end_byte, nid))
                    for child in node.children:
                        walk(child, parent_class=parent_class)
                    return
                if nt == "function_declaration":
                    fn_name = self.get_first_identifier(node)
                    if fn_name:
                        q = f"{parent_class}.{fn_name}" if parent_class else fn_name
                        nid = _node_id(file_path, q)
                        if nid in all_nodes:
                            scopes.append((node.start_byte, node.end_byte, nid))
                    for child in node.children:
                        walk(child, parent_class=parent_class)
                    return
                if nt == "export_statement":
                    for child in node.children:
                        walk(child, parent_class=parent_class)
                    return

            for child in node.children:
                walk(child, parent_class=parent_class)

        walk(root)
        return scopes

    def find_call_sites(
        self, root, language_name: str
    ) -> List[Tuple[str, Optional[str], int, int]]:
        """Walk AST and return all (callee_name, receiver_expr, line_1indexed, start_byte) tuples."""
        results: List[Tuple[str, Optional[str], int, int]] = []

        def walk(node):
            nt = node.type
            if language_name == "python" and nt == "call":
                fn_child = node.children[0] if node.children else None
                if fn_child:
                    if fn_child.type == "identifier":
                        name = fn_child.text.decode("utf-8", errors="replace")
                        results.append(
                            (name, None, node.start_point[0] + 1, node.start_byte)
                        )
                    elif fn_child.type == "attribute":
                        raw_text = fn_child.text.decode("utf-8", errors="replace")
                        if "." in raw_text:
                            receiver, name = raw_text.rsplit(".", 1)
                            results.append(
                                (
                                    name,
                                    receiver,
                                    node.start_point[0] + 1,
                                    node.start_byte,
                                )
                            )
                        else:
                            results.append(
                                (
                                    raw_text,
                                    None,
                                    node.start_point[0] + 1,
                                    node.start_byte,
                                )
                            )

            elif language_name == "python" and nt == "attribute":
                # Check for property / method-reference accesses on self or cls: self.content
                parent_t = node.parent.type if node.parent else ""
                if parent_t not in ("call", "attribute"):
                    raw_text = node.text.decode("utf-8", errors="replace")
                    if raw_text.startswith(("self.", "cls.")):
                        parts = raw_text.split(".")
                        if len(parts) == 2:
                            receiver, name = parts
                            results.append(
                                (
                                    name,
                                    receiver,
                                    node.start_point[0] + 1,
                                    node.start_byte,
                                )
                            )

            elif language_name != "python" and nt == "call_expression":
                fn_child = node.children[0] if node.children else None
                if fn_child:
                    if fn_child.type == "identifier":
                        name = fn_child.text.decode("utf-8", errors="replace")
                        results.append(
                            (name, None, node.start_point[0] + 1, node.start_byte)
                        )
                    elif fn_child.type in ("member_expression",):
                        raw_text = fn_child.text.decode("utf-8", errors="replace")
                        if "." in raw_text:
                            receiver, name = raw_text.rsplit(".", 1)
                            results.append(
                                (
                                    name,
                                    receiver,
                                    node.start_point[0] + 1,
                                    node.start_byte,
                                )
                            )
                        else:
                            results.append(
                                (
                                    raw_text,
                                    None,
                                    node.start_point[0] + 1,
                                    node.start_byte,
                                )
                            )

            elif language_name != "python" and nt == "member_expression":
                parent_t = node.parent.type if node.parent else ""
                if parent_t not in ("call_expression", "member_expression"):
                    raw_text = node.text.decode("utf-8", errors="replace")
                    if raw_text.startswith("this."):
                        parts = raw_text.split(".")
                        if len(parts) == 2:
                            receiver, name = parts
                            results.append(
                                (
                                    name,
                                    receiver,
                                    node.start_point[0] + 1,
                                    node.start_byte,
                                )
                            )

            for child in node.children:
                walk(child)

        walk(root)
        return results

    @staticmethod
    def find_enclosing_scope(
        call_byte: int,
        scopes: List[Tuple[int, int, str]],
    ) -> Optional[str]:
        """Return the narrowest scope (smallest byte range) enclosing *call_byte*."""
        best_id: Optional[str] = None
        best_size = float("inf")
        for start, end, nid in scopes:
            if start <= call_byte <= end:
                size = end - start
                if size < best_size:
                    best_size = size
                    best_id = nid
        return best_id

    def resolve_callee(
        self,
        call_name: str,
        caller_id: str,
        caller_file: str,
        defn_by_name: Dict[str, List[Symbol]],
        all_nodes: Dict[str, CallNode],
    ) -> Tuple[Optional[str], bool]:
        """Legacy fallback resolution using directory and file proximity."""
        candidates = defn_by_name.get(call_name, [])
        if not candidates:
            return None, False

        caller_dir = _file_dir(caller_file)

        same_file = [s for s in candidates if s.file_path == caller_file]
        same_dir = [
            s
            for s in candidates
            if _file_dir(s.file_path) == caller_dir and s.file_path != caller_file
        ]
        global_rest = [
            s
            for s in candidates
            if s.file_path != caller_file and _file_dir(s.file_path) != caller_dir
        ]

        def first_valid(syms: List[Symbol]) -> Tuple[Optional[str], bool]:
            valid = [
                s
                for s in syms
                if s.type in ("function", "method", "class")
                and _node_id(s.file_path, _qualified(s)) in all_nodes
            ]
            if not valid:
                return None, False
            nid = _node_id(valid[0].file_path, _qualified(valid[0]))
            return nid, len(valid) > 1

        nid, amb = first_valid(same_file)
        if nid:
            return nid, amb

        nid, amb = first_valid(same_dir)
        if nid:
            return nid, amb

        nid, amb = first_valid(global_rest)
        if nid:
            return nid, len(global_rest) > 1

        return None, False

    @staticmethod
    def get_first_identifier(node) -> str:
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                return child.text.decode("utf-8", errors="replace")
        return ""
