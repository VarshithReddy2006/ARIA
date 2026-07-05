# Roadmap — Repo Intelligence Agent

This document details the planned milestones, future enhancements, and architectural direction for the Repo Intelligence Agent platform.

Completed work and changelogs for past releases can be found in [CHANGELOG.md](CHANGELOG.md).

---

## Completed (v1.0.0)

All foundational platform layers and stabilization components have been successfully delivered:

- **Repository Ingestion & AST Parsing**: Tree-sitter integration for Python, JavaScript, and TypeScript with incremental rebuild support.
- **Topological & Call Graph Construction**: NetworkX directed graphs representing file import relationships and function call hierarchies.
- ** Grained Chat (v2)**: Intent-routed chat engine with ChromaDB vector store grounding, citations, and provider failovers.
- **Code Quality & Health Reports**: Automated scorecards measuring structural stability, API surface, hygiene, and onboarding paths.
- **VS Code Extension Integration**: CodeLens, hovers, sidebar chat, tree views, and React Flow canvases directly inside the editor.

---

## Planned (v1.1+)

### v1.1 — Code Hygiene Visualizers & API Router Extensions (Q3 2026)
- **Module Stability Router**: Implement the endpoints inside `backend/routers/stability.py` to expose instability scores and distance-from-main-sequence metrics to the IDE.
- **Dependency Smells Router**: Complete endpoint implementation inside `backend/routers/dependency_smells.py` to query high-coupling hotspots and orphan helpers.
- **Dead Code Treemap**: Add a visual tree-map canvas representing code modules sized by line counts and colored by coupling density/orphan status, making hotspots instantly recognizable.
- **Command Palette (`Ctrl+K`)**: Introduce a keyboard-driven command interface on the dashboard to trigger search queries, navigate files, swap views, and clear caches.

### v1.2 — Multi-Repository Workspaces (Q4 2026)
- **Cross-Repo Indexing**: Allow developers to load multiple repositories into a single workspace, resolving dependency linkages across microservices.
- **PR Review Assistant**: Integrate GitHub App webhooks to automatically review incoming Pull Requests, post architectural drift reports, and flag circular imports directly inside PR comment threads.
- **Incremental Indexing**: Speed up indexing updates by parsing and vector-storing only modified files on branch updates.

### v2.0 — Collaborative Multi-Agent SaaS (2027)
- **Collaborative Workspaces**: Multi-user dashboards with code indexing caches, custom team dashboards, and access permission managers.
- **SaaS Platform**: A cloud-hosted version that indexes large enterprise codebases asynchronously.
- **Plugin Ecosystem**: Enable developers to write custom Tree-sitter query modules to check for proprietary coding standards, library replacements, or custom architecture rules.
- **Distributed Agent Teams**: Spawns concurrent, specialized agents working collaboratively to solve codebase tickets.
