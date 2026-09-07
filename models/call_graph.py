"""Call Graph data models.

Defines the Pydantic schemas for the Function Call Graph intelligence layer.
Stored separately from models/schemas.py to maintain domain isolation,
following the same convention as models/churn.py, models/symbol.py, etc.

Node IDs use the format: "{file_path}::{qualifier}.{name}"
  e.g. "services/auth.py::AuthService.authenticate"
       "agents/issue_mapper.py::map_issue"
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CallRelationshipType(str, Enum):
    """Semantic classification of a function or method call relationship."""

    DIRECT_CALL = "DIRECT_CALL"
    METHOD_CALL = "METHOD_CALL"
    INSTANCE_METHOD = "INSTANCE_METHOD"
    INHERITED_CALL = "INHERITED_CALL"
    SUPER_CALL = "SUPER_CALL"
    MODULE_FUNCTION_CALL = "MODULE_FUNCTION_CALL"
    CONSTRUCTOR_CALL = "CONSTRUCTOR_CALL"
    ALIAS_CALL = "ALIAS_CALL"
    DECORATED_HANDLER = "DECORATED_HANDLER"
    UNRESOLVED_CALL = "UNRESOLVED_CALL"


class CallNode(BaseModel):
    """A single function or method node in the call graph.

    Attributes:
        node_id:      Globally unique identifier: "{file_path}::{qualifier}"
        name:         Plain function/method name (e.g. "authenticate").
        qualified:    Dot-qualified name (e.g. "AuthService.authenticate").
        file_path:    Relative file path within the repository.
        line_number:  1-indexed line of the definition.
        language:     Source language: python | javascript | typescript | tsx.
        symbol_type:  "function" | "method" | "class".
        parent_class: Enclosing class name for methods; None otherwise.
        is_entry:     True if this node has no callers (call-graph root).
        is_recursive: True if this function calls itself (directly).
        fan_in:       Number of distinct callers (in-degree in call graph).
        fan_out:      Number of distinct callees (out-degree in call graph).
    """

    node_id: str = Field(..., description="Unique node ID: file_path::qualified_name")
    name: str = Field(..., description="Plain symbol name.")
    qualified: str = Field(
        ..., description="Dot-qualified name (Class.method or function)."
    )
    file_path: str = Field(..., description="Relative file path.")
    line_number: int = Field(1, ge=1, description="1-indexed definition line.")
    language: str = Field("unknown", description="Source language.")
    symbol_type: str = Field("function", description="function | method | class")
    parent_class: Optional[str] = Field(
        None, description="Enclosing class name for methods."
    )
    is_entry: bool = Field(False, description="True if no callers (call-graph root).")
    is_recursive: bool = Field(False, description="True if directly recursive.")
    fan_in: int = Field(0, ge=0, description="Number of distinct callers.")
    fan_out: int = Field(0, ge=0, description="Number of distinct callees.")


class CallEdge(BaseModel):
    """A directed edge from caller to callee in the call graph.

    Attributes:
        caller_id:       node_id of the calling function.
        callee_id:       node_id of the called function.
        call_line:       Line number of the call expression.
        ambiguous:       True when the callee was resolved heuristically and
                         multiple matches existed — not a certain resolution.
        relationship:    CallRelationshipType semantic classification.
        receiver_expr:   Raw receiver text (e.g., "self", "session").
        receiver_type:   Statically inferred type of receiver.
        confidence_tier: Confidence tier ("HIGH", "MEDIUM", "LOW").
    """

    caller_id: str = Field(..., description="node_id of the caller.")
    callee_id: str = Field(..., description="node_id of the callee.")
    call_line: int = Field(0, ge=0, description="Line of the call expression.")
    ambiguous: bool = Field(
        False, description="True for heuristic/uncertain resolutions."
    )
    relationship: str = Field(
        CallRelationshipType.DIRECT_CALL.value,
        description="CallRelationshipType classification.",
    )
    receiver_expr: Optional[str] = Field(
        None, description="Raw receiver text (e.g. self, session)."
    )
    receiver_type: Optional[str] = Field(
        None, description="Statically inferred type of receiver."
    )
    confidence_tier: str = Field("HIGH", description="HIGH | MEDIUM | LOW")


class BlastRadiusResult(BaseModel):
    """Function-level blast radius for a single starting function.

    Attributes:
        function_id:       The starting function's node_id.
        affected_functions: All functions reachable from this one (callers-of-callers).
        affected_files:    Distinct files containing affected functions.
        depth:             Maximum propagation depth reached.
        risk_level:        "low" | "medium" | "high" based on affected count.
        recursive_cycles:  List of SCCs (cycles) in the affected subgraph.
    """

    function_id: str
    affected_functions: List[str] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    depth: int = Field(0, ge=0)
    risk_level: str = Field("low")
    recursive_cycles: List[List[str]] = Field(default_factory=list)


class CallHierarchyNode(BaseModel):
    """One node in a call hierarchy tree (for frontend rendering).

    Used by GET /api/call-graph/{owner}/{repo}/hierarchy/{function}.
    """

    node_id: str
    name: str
    qualified: str
    file_path: str
    children: List["CallHierarchyNode"] = Field(default_factory=list)
    depth: int = Field(0, ge=0)
    is_recursive_back_edge: bool = Field(
        False, description="True when this edge closes a cycle."
    )


# Required for self-referential model
CallHierarchyNode.model_rebuild()


class CallGraphSummary(BaseModel):
    """Persisted call graph index for a repository.

    Written to data/call_graphs/{owner}_{repo}.json by CallGraphService.build().

    Attributes:
        repo:           Repository identifier (owner/repo).
        generated_at:   ISO-8601 UTC timestamp.
        node_count:     Total function/method nodes.
        edge_count:     Total call edges.
        entry_functions: Node IDs with no callers (call-graph roots).
        recursive_functions: Node IDs that are directly recursive.
        top_fan_in:     Top-10 most-called functions.
        top_fan_out:    Top-10 functions that call the most others.
        warning:        Optional diagnostic warning.
    """

    repo: str
    generated_at: str
    node_count: int = Field(0, ge=0)
    edge_count: int = Field(0, ge=0)
    entry_functions: List[str] = Field(default_factory=list)
    recursive_functions: List[str] = Field(default_factory=list)
    top_fan_in: List[Dict[str, object]] = Field(default_factory=list)
    top_fan_out: List[Dict[str, object]] = Field(default_factory=list)
    warning: Optional[str] = None
