"""Model Context Protocol (MCP) Stdio Server.

Exposes ARIA's analysis engines (symbols, call graphs,
dependency graphs, dead code, PR analysis, and retrieval) as standard MCP tools.
"""

import json
import os
import sys

# Limit OpenBLAS / MKL / OMP threads in MCP stdio subprocess to prevent memory exhaustion
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import traceback
import logging
from typing import Dict, Any, List, Optional

# Redirect all root logging to stderr. Stdout MUST be preserved exclusively for JSON-RPC.
logger = logging.getLogger()
for handler in list(logger.handlers):
    logger.removeHandler(handler)
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setFormatter(
    logging.Formatter("[MCP Log] %(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(stderr_handler)
logger.setLevel(logging.INFO)

# Expose tools definition list
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "list_repositories",
        "description": "Lists all repositories currently analyzed and persisted in the system.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_repository_summary",
        "description": "Retrieves the parsed tech stack, dependency declarations, and high-level structure of a repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Owner/organization name"},
                "repo": {"type": "string", "description": "Repository name"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "get_file_symbols",
        "description": "Returns all classes, functions, and methods defined inside a specific source file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "file_path": {
                    "type": "string",
                    "description": "Relative file path (e.g. core/cache.py)",
                },
            },
            "required": ["owner", "repo", "file_path"],
        },
    },
    {
        "name": "get_symbol_definition",
        "description": "Looks up the definition location and signature of a specific symbol.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "symbol_name": {
                    "type": "string",
                    "description": "Name of the class, function, or method",
                },
            },
            "required": ["owner", "repo", "symbol_name"],
        },
    },
    {
        "name": "get_symbol_references",
        "description": "Returns all file occurrences and usages of a specific symbol in the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "symbol_name": {"type": "string", "description": "Name of the symbol"},
            },
            "required": ["owner", "repo", "symbol_name"],
        },
    },
    {
        "name": "get_call_graph",
        "description": "Retrieves call graph statistics and relations for a repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "get_dead_code",
        "description": "Retrieves orphaned modules and unreachable code paths in the repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "query_codebase",
        "description": "Runs a context-grounded natural language search query over the repository files (RAG chat).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "query": {
                    "type": "string",
                    "description": "Question or query text about the code",
                },
            },
            "required": ["owner", "repo", "query"],
        },
    },
]


# Schema lookup derived from TOOLS so validation and advertised contract cannot drift.
_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {t["name"]: t["inputSchema"] for t in TOOLS}


class InvalidParams(Exception):
    """Arguments failed contract validation; maps to JSON-RPC -32602."""


def validate_tool_arguments(tool_name: str, arguments: Any) -> Dict[str, Any]:
    """Validate ``arguments`` against the tool's advertised inputSchema.

    Runs before any service call so malformed input can never reach the
    business layer. Returns the normalised argument dict (strings trimmed).
    Raises :class:`InvalidParams` on any violation.

    Unknown properties are ignored rather than rejected, matching JSON Schema's
    default ``additionalProperties`` behaviour, so a newer client sending an
    extra hint field is not broken by an older server.
    """
    schema = _TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        raise InvalidParams(f"Unknown tool '{tool_name}'.")
    if not isinstance(arguments, dict):
        raise InvalidParams(
            f"'arguments' must be a JSON object, got {type(arguments).__name__}."
        )

    properties: Dict[str, Any] = schema.get("properties", {})
    missing = [f for f in schema.get("required", []) if f not in arguments]
    if missing:
        raise InvalidParams(
            "Missing required argument(s): " + ", ".join(sorted(missing)) + "."
        )

    validated: Dict[str, Any] = {}
    for key, value in arguments.items():
        spec = properties.get(key)
        if spec is None:
            continue
        if spec.get("type") == "string":
            if not isinstance(value, str):
                raise InvalidParams(
                    f"Argument '{key}' must be a string, got {type(value).__name__}."
                )
            trimmed = value.strip()
            if not trimmed:
                raise InvalidParams(f"Argument '{key}' must not be empty.")
            validated[key] = trimmed
        else:
            validated[key] = value
    return validated


def send_response(response: Dict[str, Any]) -> None:
    """Helper to dump response JSON to standard output."""
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


_TRUTHY = {"1", "true", "yes", "on"}


def _debug_errors_enabled() -> bool:
    """True when the operator has opted in to verbose client-visible errors.

    Read per-call rather than cached at import so the flag can be toggled in
    tests and by wrappers without reloading the module.
    """
    return os.environ.get("MCP_DEBUG_ERRORS", "").strip().lower() in _TRUTHY


def _client_safe_message(tool_name: str, exc: Exception) -> str:
    """Return a concise, non-revealing message for a failed tool call.

    ``ValueError`` is the deliberate signal for domain conditions ("repository
    not indexed", "symbol not found"); its text is curated and safe to forward.
    Every other exception type is unplanned and may embed paths, SQL, or
    internal identifiers, so it is redacted to a fixed string. The full detail
    always reaches the server log.
    """
    if isinstance(exc, ValueError):
        message = str(exc).strip()
        if message:
            return message
    return f"Tool '{tool_name}' failed due to an internal error."


def _error_data(exc: Exception) -> Dict[str, Any]:
    """Optional ``data`` member; carries a traceback only in explicit debug mode."""
    if _debug_errors_enabled():
        return {"data": traceback.format_exc()}
    return {}


def run_mcp_server() -> None:
    """Main loop reading JSON-RPC requests from stdin and responding to stdout."""
    logger.info("Initializing ARIA MCP Server...")

    # Hydrate persisted repositories from disk. The FastAPI app does this in its
    # startup path; the stdio server has no lifespan hook, so without this every
    # repository-scoped tool reports "not indexed". Guarded on emptiness so the
    # call is idempotent and never re-validates an already-populated store.
    from backend.dependencies import ANALYSIS_STORE, _load_analysis_store

    if not ANALYSIS_STORE:
        _load_analysis_store()
    logger.info("Analysis store ready: %d repositories available.", len(ANALYSIS_STORE))

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # 1. Initialization handshake
            if method == "initialize":
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "repo-intelligence-mcp",
                                "version": "1.5.0",
                            },
                        },
                    }
                )

            # 2. List tools
            elif method == "tools/list":
                send_response(
                    {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
                )

            # 3. Call tool
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                # Contract validation runs before any service call, so invalid
                # input is rejected as -32602 and never reaches business logic.
                try:
                    arguments = validate_tool_arguments(tool_name, arguments)
                except InvalidParams as bad_params:
                    logger.warning(
                        "Rejected tools/call for %r: %s", tool_name, bad_params
                    )
                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32602,
                                "message": f"Invalid params: {bad_params}",
                            },
                        }
                    )
                    continue

                result_content = []
                try:
                    tool_result = execute_tool(
                        tool_name,
                        arguments,
                        ANALYSIS_STORE,
                    )
                    result_content.append(
                        {"type": "text", "text": json.dumps(tool_result, indent=2)}
                    )
                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {"content": result_content},
                        }
                    )
                except Exception as tool_err:
                    # Full traceback to the server log (stderr), never to the client
                    # unless MCP_DEBUG_ERRORS is explicitly set.
                    logger.error(
                        "Tool %s failed: %s", tool_name, tool_err, exc_info=True
                    )
                    # A failing tool is an execution outcome, not a transport
                    # fault, so MCP requires it be reported as a successful
                    # result carrying isError. JSON-RPC error codes stay
                    # reserved for protocol-level problems.
                    message = _client_safe_message(tool_name, tool_err)
                    if _debug_errors_enabled():
                        message = f"{message}\n\n{traceback.format_exc()}"
                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": message}],
                                "isError": True,
                            },
                        }
                    )

            # 4. Shutdown request
            elif method in ("shutdown", "exit"):
                if req_id is not None:
                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {"status": "shutdown"},
                        }
                    )
                break

            # 5. Unknown/unsupported JSON-RPC method
            else:
                if req_id is not None:
                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32601,
                                "message": f"Method {method} not found.",
                            },
                        }
                    )
        except Exception as exc:
            logger.error("Error handling MCP request: %s", exc, exc_info=True)
            # If the request could not be parsed, send a generic error.
            send_response(
                {
                    "jsonrpc": "2.0",
                    # JSON-RPC 2.0: when the request id cannot be determined,
                    # the response id MUST be null rather than omitted.
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": "Parse error",
                        **_error_data(exc),
                    },
                }
            )


def execute_tool(
    name: str,
    args: Dict[str, Any],
    store: Optional[Dict[str, Any]] = None,
    symbols: Any = None,
    call_graph: Any = None,
    dead_code: Any = None,
    retrieval: Any = None,
) -> Any:
    """Invokes the corresponding backend service and returns serializable data."""
    import backend.dependencies as deps

    if store is None:
        store = deps.ANALYSIS_STORE

    if name == "list_repositories":
        return list(store.keys())

    owner = args.get("owner", "").strip()
    repo = args.get("repo", "").strip()
    repo_name = f"{owner}/{repo}"

    if name == "get_repository_summary":
        if repo_name not in store:
            raise ValueError(
                f"Repository '{repo_name}' is not indexed. Analyze it first."
            )
        entry = store[repo_name]
        return {
            "analysis": entry["analysis"].model_dump()
            if hasattr(entry["analysis"], "model_dump")
            else entry["analysis"],
            "architecture": entry["architecture"].model_dump()
            if hasattr(entry["architecture"], "model_dump")
            else entry["architecture"],
        }

    elif name == "get_file_symbols":
        if symbols is None:
            symbols = deps.symbol_service
        file_path = args.get("file_path", "").strip()
        res = symbols.get_file_symbols(repo_name, file_path)
        if res is None:
            raise ValueError(
                f"No symbol index found for file '{file_path}' in repo '{repo_name}'."
            )
        return [s.model_dump() for s in res]

    elif name == "get_symbol_definition":
        if symbols is None:
            symbols = deps.symbol_service
        sym_name = args.get("symbol_name", "").strip()
        res = symbols.get_definition(repo_name, sym_name)
        if res is None:
            raise ValueError(f"Symbol '{sym_name}' not found in repo '{repo_name}'.")
        return res.model_dump()

    elif name == "get_symbol_references":
        if symbols is None:
            symbols = deps.symbol_service
        sym_name = args.get("symbol_name", "").strip()
        # get_references is typed Optional[List[Symbol]] and returns None when the
        # repository has no symbol index. "No references" is a valid answer, so
        # normalise to an empty list rather than raising.
        res = symbols.get_references(repo_name, sym_name)
        return [s.model_dump() for s in (res or [])]

    elif name == "get_call_graph":
        if call_graph is None:
            call_graph = deps.call_graph_service
        # CallGraphService exposes the persisted summary as load_summary(); the
        # previous get_graph_summary() name does not exist on the service.
        res = call_graph.load_summary(repo_name)
        if res is None:
            raise ValueError(f"No call graph indexed for '{repo_name}'.")
        return res.model_dump()

    elif name == "get_dead_code":
        # Check if repo metadata exists
        if repo_name not in store:
            raise ValueError(f"Repository '{repo_name}' is not indexed.")
        store[repo_name]["analysis"].metadata.get("local_path", "")
        # Run dead code sweep
        from services.dead_code_service import DeadCodeService

        dc_service = (
            dead_code
            if (dead_code is not None and hasattr(dead_code, "analyze"))
            else DeadCodeService()
        )
        dc_service.github_service = deps.github_service
        dc_service.graph_service = deps.graph_service
        dc_service.architecture_service = deps.architecture_service

        # Build graphs if not existing
        res = dc_service.analyze(repo_name)
        return res.model_dump()

    elif name == "query_codebase":
        if retrieval is None:
            retrieval = deps.retrieval_service
        query = args.get("query", "").strip()
        # RetrievalService's public entry point is retrieve_and_answer(); it
        # returns the same answer/sources/confidence/verified shape used below.
        res = retrieval.retrieve_and_answer(repo_name, query)
        return {
            "answer": res.get("answer", ""),
            "sources": [
                s.model_dump() if hasattr(s, "model_dump") else s
                for s in res.get("sources", [])
            ],
            "confidence": res.get("confidence", 0.0),
            "verified": res.get("verified", False),
        }

    else:
        raise ValueError(f"Tool {name} is not supported.")
