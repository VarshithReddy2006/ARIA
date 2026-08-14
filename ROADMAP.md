# Roadmap — ARIA

This document details the planned milestones, future enhancements, and architectural direction for the ARIA platform.

Completed work and changelogs for past releases can be found in [CHANGELOG.md](CHANGELOG.md).

---

## Completed (v1.5.0)

All foundational platform layers and stabilization components have been successfully delivered:

- **Repository Intelligence Architecture (RIA v1)**: Modular, layered production architecture organizing the platform into Agent, Application, Domain, Infrastructure, Production MCP Integration Layer, API, Extension, and Dashboard layers.
- **Production MCP Integration Layer**: First-class subsystem exposing codebase intelligence over JSON-RPC 2.0.
- **Dual MCP Server Architecture**: Dual implementation comprising Legacy stdio server (`backend/mcp_server.py`) and FastMCP server (`mcp/server.py`).
- **Legacy JSON-RPC Server**: Lightweight stdio protocol server with zero external SDK dependencies.
- **FastMCP Server**: FastMCP SDK integration supporting automatic tool discovery, resource templates, prompt templates, and SSE transport.
- **MCP Resources**: Repository-scoped structured data resources.
- **MCP Prompt Templates**: Pre-built analysis workflows for external AI assistants.
- **MCP Inspector Validation**: 100% of MCP tools manually validated via interactive Inspector sessions.
- **Cursor Compatibility**: Fully verified and compatible with Cursor IDE.
- **Claude Desktop Compatibility**: Fully verified and compatible with Claude Desktop.
- **VS Code MCP Compatibility**: Fully verified and compatible with VS Code MCP extension client.
- **Repository Ingestion & AST Parsing**: Tree-sitter integration for Python, JavaScript, and TypeScript with incremental rebuild support.
- **Topological & Call Graph Construction**: NetworkX directed graphs representing file import relationships and function call hierarchies.
- **Fine-Grained Chat (v2)**: Intent-routed chat engine with ChromaDB vector store grounding, citations, and provider failovers.
- **Code Quality & Health Reports**: Automated scorecards measuring structural stability, API surface, hygiene, and onboarding paths.
- **VS Code Extension Integration**: CodeLens, hovers, sidebar chat, tree views, and React Flow canvases directly inside the editor.
- **AI Repository Intelligence**: Graph-based code understanding with semantic search, symbol indexing, and structural context.
- **Cross-platform Validation**: Validated on Windows, Linux, and macOS with 2505 automated tests.
- **Production Documentation**: Authoritative architecture specs, API guides, release readiness reports, and audit logs.
- **SDK Compatibility Validation**: Verified tool registration and model reflection across Pydantic and FastMCP SDK versions.
- **JSON-RPC 2.0 Compliance Validation**: Protocol-compliant frame serialization, error handling, and notifications over stdio pipes.

---

## Planned (v1.6.0)

### v1.6.0 — Code Hygiene Visualizers & API Router Extensions (Q3 2026)
- **Module Stability Router**: Implement the endpoints inside `backend/routers/stability.py` to expose instability scores and distance-from-main-sequence metrics to the IDE.
- **Dependency Smells Router**: Complete endpoint implementation inside `backend/routers/dependency_smells.py` to query high-coupling hotspots and orphan helpers.
- **Dead Code Treemap**: Add a visual tree-map canvas representing code modules sized by line counts and colored by coupling density/orphan status, making hotspots instantly recognizable.
- **Command Palette (`Ctrl+K`)**: Introduce a keyboard-driven command interface on the dashboard to trigger search queries, navigate files, swap views, and clear caches.

### Planned (v1.7.0) — Multi-Repository Workspaces (Q4 2026)
- **Cross-Repo Indexing**: Allow developers to load multiple repositories into a single workspace, resolving dependency linkages across microservices.
- **PR Review Assistant**: Integrate GitHub App webhooks to automatically review incoming Pull Requests, post architectural drift reports, and flag circular imports directly inside PR comment threads.
- **Incremental Indexing**: Speed up indexing updates by parsing and vector-storing only modified files on branch updates.

### Long-Term Vision (v2.0) — Collaborative Multi-Agent SaaS (2027)
- **Collaborative Workspaces**: Multi-user dashboards with code indexing caches, custom team dashboards, and access permission managers.
- **SaaS Platform**: A cloud-hosted version that indexes large enterprise codebases asynchronously.
- **Plugin Ecosystem**: Enable developers to write custom Tree-sitter query modules to check for proprietary coding standards, library replacements, or custom architecture rules.
- **Distributed Agent Teams**: Spawns concurrent, specialized agents working collaboratively to solve codebase tickets.
