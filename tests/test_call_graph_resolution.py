"""Unit tests for ARIA v6 Semantic Call Graph & Cross-Language Symbol Resolution.

Tests the semantic resolution capabilities:
1. Exact function call resolution (DIRECT_CALL)
2. Import alias resolution (ALIAS_CALL)
3. Qualified method calls (METHOD_CALL)
4. Instance method calls (INSTANCE_METHOD)
5. Same-name method disambiguation across different classes
6. Base class inheritance resolution (INHERITED_CALL)
7. super() method calls (SUPER_CALL)
8. Unresolved dynamic calls marked as UNRESOLVED_CALL (UNCERTAIN, LOW confidence)
9. Snapshot-aware CallSiteIndex caching and traversal
"""

from __future__ import annotations

import networkx as nx
import pytest

from models.call_graph import CallNode, CallRelationshipType
from models.symbol import Symbol
from services.call_graph.semantic_resolver import (
    ClassHierarchyIndex,
    FileImportTable,
    ScopeTypeInferrer,
    SemanticCallResolver,
)
from services.call_site_index import CallSiteIndex


@pytest.fixture
def empty_hierarchy() -> ClassHierarchyIndex:
    return ClassHierarchyIndex()


def test_import_table_python_resolution():
    """Verify parsing and symbol resolution in FileImportTable for Python."""
    code = """
import os
import requests.sessions as sess_mod
from requests.sessions import Session, SessionRedirectMixin as RedirMixin
from core.utils import helper
"""
    table = FileImportTable.parse_source("src/app.py", code, "python")
    assert table.module_imports["os"] == "os"
    assert table.module_imports["sess_mod"] == "requests.sessions"
    assert table.symbol_imports["Session"] == ("requests.sessions", "Session")
    assert table.symbol_imports["RedirMixin"] == (
        "requests.sessions",
        "SessionRedirectMixin",
    )
    assert table.symbol_imports["helper"] == ("core.utils", "helper")


def test_import_table_javascript_resolution():
    """Verify parsing and symbol resolution in FileImportTable for JS/TS."""
    code = """
import { Session, Client as MyClient } from './sessions';
import express from 'express';
const utils = require('./utils');
"""
    table = FileImportTable.parse_source("src/index.ts", code, "typescript")
    assert table.symbol_imports["Session"] == ("src/sessions", "Session")
    assert table.symbol_imports["MyClient"] == ("src/sessions", "Client")
    assert table.module_imports["express"] == "express"
    assert table.module_imports["utils"] == "src/utils"


def test_class_hierarchy_mro_and_inheritance():
    """Verify ClassHierarchyIndex correctly tracks inheritance and resolves inherited methods."""
    h = ClassHierarchyIndex()
    h.register_class("src/base.py", "BaseAdapter", [])
    h.register_method("src/base.py", "BaseAdapter", "send")
    h.register_method("src/base.py", "BaseAdapter", "close")

    h.register_class("src/http.py", "HTTPAdapter", ["BaseAdapter"])
    h.register_method(
        "src/http.py", "HTTPAdapter", "send"
    )  # Overrides BaseAdapter.send

    # 1. HTTPAdapter.send is defined directly on HTTPAdapter -> METHOD_CALL
    found = h.find_method_definition("HTTPAdapter", "send", "src/http.py")
    assert found is not None
    def_file, def_class, rel = found
    assert def_file == "src/http.py"
    assert def_class == "HTTPAdapter"
    assert rel == CallRelationshipType.METHOD_CALL.value

    # 2. HTTPAdapter.close is inherited from BaseAdapter -> INHERITED_CALL
    found = h.find_method_definition("HTTPAdapter", "close", "src/http.py")
    assert found is not None
    def_file, def_class, rel = found
    assert def_file == "src/base.py"
    assert def_class == "BaseAdapter"
    assert rel == CallRelationshipType.INHERITED_CALL.value


def test_same_name_disambiguation_across_classes():
    """Verify that same-name methods on different classes resolve strictly to their receiver."""
    all_nodes = {
        "src/sessions.py::Session.send": CallNode(
            node_id="src/sessions.py::Session.send",
            name="send",
            qualified="Session.send",
            file_path="src/sessions.py",
            line_number=10,
        ),
        "src/adapters.py::HTTPAdapter.send": CallNode(
            node_id="src/adapters.py::HTTPAdapter.send",
            name="send",
            qualified="HTTPAdapter.send",
            file_path="src/adapters.py",
            line_number=50,
        ),
        "src/adapters.py::BaseAdapter.send": CallNode(
            node_id="src/adapters.py::BaseAdapter.send",
            name="send",
            qualified="BaseAdapter.send",
            file_path="src/adapters.py",
            line_number=100,
        ),
    }

    h = ClassHierarchyIndex()
    h.register_class("src/sessions.py", "Session", [])
    h.register_method("src/sessions.py", "Session", "send")
    h.register_class("src/adapters.py", "HTTPAdapter", [])
    h.register_method("src/adapters.py", "HTTPAdapter", "send")

    defn_by_name = {
        "send": [
            Symbol(
                name="send",
                type="method",
                file_path="src/sessions.py",
                line_number=10,
                parent_class="Session",
                language="python",
            ),
            Symbol(
                name="send",
                type="method",
                file_path="src/adapters.py",
                line_number=50,
                parent_class="HTTPAdapter",
                language="python",
            ),
        ]
    }

    resolver = SemanticCallResolver(all_nodes, defn_by_name, h)

    # Inferrer where receiver 'adapter' is HTTPAdapter
    inferrer_adapter = ScopeTypeInferrer("src/test.py")
    inferrer_adapter.var_types["adapter"] = "HTTPAdapter"

    callee_id, rel, rec_type, conf, amb = resolver.resolve_call(
        caller_id="src/test.py::test_fn",
        caller_file="src/test.py",
        callee_name="send",
        receiver_expr="adapter",
        type_inferrer=inferrer_adapter,
        call_line=25,
    )
    assert callee_id == "src/adapters.py::HTTPAdapter.send"
    assert rel == CallRelationshipType.INSTANCE_METHOD.value
    assert rec_type == "HTTPAdapter"
    assert conf == "HIGH"

    # Inferrer where receiver 's' is Session
    inferrer_session = ScopeTypeInferrer("src/test.py")
    inferrer_session.var_types["s"] = "Session"

    callee_id2, rel2, rec_type2, conf2, amb2 = resolver.resolve_call(
        caller_id="src/test.py::test_fn2",
        caller_file="src/test.py",
        callee_name="send",
        receiver_expr="s",
        type_inferrer=inferrer_session,
        call_line=30,
    )
    assert callee_id2 == "src/sessions.py::Session.send"
    assert rel2 == CallRelationshipType.INSTANCE_METHOD.value
    assert rec_type2 == "Session"
    assert conf2 == "HIGH"


def test_scope_type_inference_patterns():
    """Verify ScopeTypeInferrer captures assignments, annotations, and with statements."""
    import ast

    code = """
def process_data(session: Session, count: int):
    client = TestClient()
    adapter: HTTPAdapter = get_adapter()
    with ContextSession() as ctx_sess:
        pass
"""
    tree = ast.parse(code)
    fn_node = tree.body[0]
    inferrer = ScopeTypeInferrer("src/handlers.py")
    inferrer.scan_python_function(fn_node)

    assert inferrer.var_types.get("session") == "Session"
    assert inferrer.var_types.get("client") == "TestClient"
    assert inferrer.var_types.get("adapter") == "HTTPAdapter"
    assert inferrer.var_types.get("ctx_sess") == "ContextSession"


def test_import_alias_resolution():
    """Verify imported aliases resolve to the canonical definition with ALIAS_CALL."""
    all_nodes = {
        "src/sessions.py::Session": CallNode(
            node_id="src/sessions.py::Session",
            name="Session",
            qualified="Session",
            file_path="src/sessions.py",
            line_number=1,
            symbol_type="class",
        )
    }
    h = ClassHierarchyIndex()
    resolver = SemanticCallResolver(all_nodes, {}, h)

    code = "from src.sessions import Session as CustomSession"
    table = FileImportTable.parse_source("src/app.py", code, "python")
    resolver.import_tables["src/app.py"] = table

    callee_id, rel, rec_type, conf, amb = resolver.resolve_call(
        caller_id="src/app.py::main",
        caller_file="src/app.py",
        callee_name="CustomSession",
        receiver_expr=None,
        type_inferrer=None,
        call_line=5,
    )
    assert callee_id == "src/sessions.py::Session"
    assert rel == CallRelationshipType.ALIAS_CALL.value
    assert conf == "HIGH"


def test_super_call_resolution():
    """Verify super().method() resolves to base class method definition with SUPER_CALL."""
    all_nodes = {
        "src/base.py::BaseService.init_app": CallNode(
            node_id="src/base.py::BaseService.init_app",
            name="init_app",
            qualified="BaseService.init_app",
            file_path="src/base.py",
            line_number=5,
        ),
        "src/derived.py::CustomService.init_app": CallNode(
            node_id="src/derived.py::CustomService.init_app",
            name="init_app",
            qualified="CustomService.init_app",
            file_path="src/derived.py",
            line_number=12,
        ),
    }

    h = ClassHierarchyIndex()
    h.register_class("src/base.py", "BaseService", [])
    h.register_method("src/base.py", "BaseService", "init_app")
    h.register_class("src/derived.py", "CustomService", ["BaseService"])
    h.register_method("src/derived.py", "CustomService", "init_app")

    resolver = SemanticCallResolver(all_nodes, {}, h)

    callee_id, rel, rec_type, conf, amb = resolver.resolve_call(
        caller_id="src/derived.py::CustomService.init_app",
        caller_file="src/derived.py",
        callee_name="init_app",
        receiver_expr="super()",
        type_inferrer=None,
        call_line=13,
    )
    assert callee_id == "src/base.py::BaseService.init_app"
    assert rel == CallRelationshipType.SUPER_CALL.value
    assert rec_type == "BaseService"
    assert conf == "HIGH"


def test_unresolved_dynamic_call_marked_uncertain():
    """Verify dynamic calls without type info or resolution are marked UNRESOLVED_CALL and LOW confidence."""
    all_nodes = {
        "src/util.py::execute": CallNode(
            node_id="src/util.py::execute",
            name="execute",
            qualified="execute",
            file_path="src/util.py",
            line_number=1,
        )
    }
    h = ClassHierarchyIndex()
    resolver = SemanticCallResolver(all_nodes, {}, h)

    # Dynamic call: obj.unknown_method()
    callee_id, rel, rec_type, conf, amb = resolver.resolve_call(
        caller_id="src/main.py::run",
        caller_file="src/main.py",
        callee_name="unknown_method",
        receiver_expr="dynamic_obj",
        type_inferrer=None,
        call_line=15,
    )
    assert callee_id is None
    assert rel == CallRelationshipType.UNRESOLVED_CALL.value
    assert conf == "LOW"


def test_call_site_index_bounded_traversal():
    """Verify CallSiteIndex caches graph and resolves direct and transitive callers."""
    cg = nx.DiGraph()
    cg.add_node(
        "services/token.py::verify_token",
        line_number=10,
        name="verify_token",
        symbol_type="function",
    )
    cg.add_node(
        "services/auth.py::auth_middleware",
        line_number=55,
        name="auth_middleware",
        symbol_type="function",
    )
    cg.add_node(
        "routers/api.py::route_handler",
        line_number=100,
        name="route_handler",
        symbol_type="function",
    )

    cg.add_edge(
        "services/auth.py::auth_middleware",
        "services/token.py::verify_token",
        relationship="DIRECT_CALL",
        confidence_tier="HIGH",
    )
    cg.add_edge(
        "routers/api.py::route_handler",
        "services/auth.py::auth_middleware",
        relationship="DIRECT_CALL",
        confidence_tier="HIGH",
    )

    index = CallSiteIndex("test/repo", "test_commit_sha")
    index.populate_from_graph(cg)

    direct, transitive = index.resolve_callers(
        {"services/token.py::verify_token"}, max_depth=3
    )
    assert len(direct) == 1
    assert direct[0].caller_name == "auth_middleware"
    assert direct[0].depth == 1

    assert len(transitive) == 1
    assert transitive[0].caller_name == "route_handler"
    assert transitive[0].depth == 2
