"""CLI Argument Parser."""

import argparse


def create_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ria", description="ARIA (RIA v2 CLI)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ria init
    init_p = subparsers.add_parser("init", help="Initialize & register a repository")
    init_p.add_argument(
        "--remote-url", required=True, help="Remote Git URL or local repository path"
    )
    init_p.add_argument("--name", required=True, help="Repository name")

    # ria index
    idx_p = subparsers.add_parser("index", help="Index repository")
    idx_p.add_argument("--repo-id", required=True, help="Repository ID")

    # ria update
    upd_p = subparsers.add_parser(
        "update", help="Synchronize and incremental reindex repository"
    )
    upd_p.add_argument("--repo-id", required=True, help="Repository ID")

    # ria search
    srch_p = subparsers.add_parser("search", help="Execute deterministic search query")
    srch_p.add_argument("--repo-id", required=True, help="Repository ID")
    srch_p.add_argument("--query", required=True, help="Search query text")

    # ria query
    q_p = subparsers.add_parser("query", help="Execute semantic query")
    q_p.add_argument("--repo-id", required=True, help="Repository ID")
    q_p.add_argument("--type", required=True, help="Query type")
    q_p.add_argument("--symbol", help="Symbol moniker")

    # ria context
    ctx_p = subparsers.add_parser("context", help="Assemble semantic context package")
    ctx_p.add_argument("--repo-id", required=True, help="Repository ID")
    ctx_p.add_argument("--question", required=True, help="Question text")
    ctx_p.add_argument(
        "--max-tokens", type=int, default=4000, help="Maximum token budget"
    )

    # ria ask
    ask_p = subparsers.add_parser("ask", help="Ask grounded natural language question")
    ask_p.add_argument("--repo-id", required=True, help="Repository ID")
    ask_p.add_argument("--question", required=True, help="Question text")

    # ria status
    stat_p = subparsers.add_parser(
        "status", help="Get repository synchronization status"
    )
    stat_p.add_argument("--repo-id", required=True, help="Repository ID")

    # ria version
    subparsers.add_parser("version", help="Print version information")

    # ria doctor
    subparsers.add_parser("doctor", help="Run system diagnostics")

    # ria config
    subparsers.add_parser("config", help="View configuration settings")

    return parser
