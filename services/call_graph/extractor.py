"""Call Graph Extractor.

Responsible for parsing source files using Tree-sitter, extracting call sites,
building function scope maps, and resolving callee symbol definitions.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

from models.call_graph import CallNode
from models.symbol import Symbol
from services.tree_sitter_service import TreeSitterService, _LANGUAGE_REGISTRY

logger = logging.getLogger(__name__)


def _node_id(file_path: str, qualified: str) -> str:
    """Build a globally unique node ID."""
    return f"{file_path}::{qualified}"


def _qualified(symbol: Symbol) -> str:
    """Build the dot-qualified name from a Symbol."""
    if symbol.parent_class:
        return f"{symbol.parent_class}.{symbol.name}"
    return symbol.name


def _file_dir(file_path: str) -> str:
    """Return the directory portion of a normalised path."""
    return "/".join(file_path.replace("\\", "/").split("/")[:-1])


class CallGraphExtractor:
    """Extracts function call edges from AST nodes using Tree-sitter."""

    def __init__(self, tree_sitter_service: Optional[TreeSitterService] = None) -> None:
        self._ts = tree_sitter_service or TreeSitterService()

    def extract_call_edges(
        self,
        file_path: str,
        content: str,
        defn_by_name: Dict[str, List[Symbol]],
        all_nodes: Dict[str, CallNode],
    ) -> List[Tuple[str, str, int, bool]]:
        """Walk the AST and extract call edges for all functions in *file_path*.

        Returns list of (caller_id, callee_id, call_line, ambiguous) tuples.
        Only emits edges where both caller and callee nodes already exist in
        all_nodes (no fabricated nodes).
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

        # Build file-local function scope stack:
        # maps (start_byte, end_byte) → caller_node_id
        scopes = self.build_scope_map(
            tree.root_node, file_path, all_nodes, language_name
        )

        # Extract all call expressions from the AST
        call_sites = self.find_call_sites(tree.root_node, language_name)

        edges: List[Tuple[str, str, int, bool]] = []
        for call_name, call_line, call_byte in call_sites:
            # Find the enclosing function scope
            caller_id = self.find_enclosing_scope(call_byte, scopes)
            if caller_id is None:
                continue  # call outside any tracked function

            # Resolve callee
            callee_id, ambiguous = self.resolve_callee(
                call_name, caller_id, file_path, defn_by_name, all_nodes
            )
            if callee_id is None:
                continue  # unresolved (external library or dynamic call)

            if caller_id == callee_id:
                # Direct recursion — always certain
                edges.append((caller_id, callee_id, call_line, False))
            else:
                edges.append((caller_id, callee_id, call_line, ambiguous))

        return edges

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

    def find_call_sites(self, root, language_name: str) -> List[Tuple[str, int, int]]:
        """Walk AST and return all (callee_name, line_1indexed, start_byte) tuples."""
        results: List[Tuple[str, int, int]] = []

        def walk(node):
            nt = node.type
            if language_name == "python" and nt == "call":
                # Python: call → (attribute|identifier) + arguments
                fn_child = node.children[0] if node.children else None
                if fn_child:
                    if fn_child.type == "identifier":
                        name = fn_child.text.decode("utf-8", errors="replace")
                        results.append((name, node.start_point[0] + 1, node.start_byte))
                    elif fn_child.type == "attribute":
                        # obj.method(…) — extract method name only
                        children = fn_child.children
                        if children:
                            last = children[-1]
                            if last.type in ("identifier", "property_identifier"):
                                name = last.text.decode("utf-8", errors="replace")
                                results.append(
                                    (name, node.start_point[0] + 1, node.start_byte)
                                )

            elif language_name != "python" and nt == "call_expression":
                fn_child = node.children[0] if node.children else None
                if fn_child:
                    if fn_child.type == "identifier":
                        name = fn_child.text.decode("utf-8", errors="replace")
                        results.append((name, node.start_point[0] + 1, node.start_byte))
                    elif fn_child.type in ("member_expression",):
                        # obj.method(…)
                        children = fn_child.children
                        if children:
                            last = children[-1]
                            if last.type in ("property_identifier", "identifier"):
                                name = last.text.decode("utf-8", errors="replace")
                                results.append(
                                    (name, node.start_point[0] + 1, node.start_byte)
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
        """Resolve a call_name to a node_id using scope-based disambiguation.

        Priority:
          1. Same file, exact name match
          2. Same directory, exact name match
          3. Any file, exact name match (possibly ambiguous)

        Returns (node_id, ambiguous). Never fabricates a node.
        """
        candidates = defn_by_name.get(call_name, [])
        if not candidates:
            return None, False

        caller_dir = _file_dir(caller_file)

        # Score each candidate
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
                if s.type in ("function", "method")
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
            return nid, len(
                global_rest
            ) > 1  # global match is always potentially ambiguous

        return None, False

    @staticmethod
    def get_first_identifier(node) -> str:
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                return child.text.decode("utf-8", errors="replace")
        return ""
