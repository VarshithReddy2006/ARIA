# ARIA — VS Code Extension Documentation

> **First-class Visual Studio Code integration for the Repository Intelligence Platform.**  
> The extension acts purely as a client to the Repository Intelligence Backend, bringing grounded code intelligence, interactive graphs, repository chat, CodeLens, hover cards, and architectural reviews directly into VS Code.

---

## 1. Architecture

```
                  Developer (VS Code IDE)
                            │
                            ▼
                VS Code Extension (Client)
        ┌───────────────────┼───────────────────┐
        │                   │                   │
  Sidebar Views       CodeLens & Hover    Webview Panels
  (Explorer, Graph,   (Context Actions,   (Diagrams, Call Graph,
   Architecture)      Hover Cards)        Architecture)
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
              Extension API Client Layer
              (BackendClient & SSEStreamClient)
                            │
                            ▼
               Repository Intelligence Backend
                            │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
Deterministic Engine   Knowledge Graph       Architecture Engine
       │                     │                     │
       └─────────────────────┼─────────────────────┘
                            │
                            ▼
              Streaming Engineering Responses
```

---

## 2. Key Features

- **Grounded Repository Chat**:
  - Interactive sidebar chat supported by deterministic retrieval and symbol-grounded responses.
  - Evidence First Response Format: Displays **Evidence $\rightarrow$ Reasoning $\rightarrow$ Explanation $\rightarrow$ Recommendations**.

- **Editor Integration**:
  - **CodeLens**: Annotates functions and classes with quick actions (`Explain`, `Trace`, `Dependencies`, `Architecture`, `Impact`, `Review`).
  - **Hover Provider**: Displays rich Markdown hover cards containing symbol type, file location, architecture layer, dependencies, callers (fan-in), callees (fan-out), and quality metrics.
  - **Right-Click Context Menu**: Editor & File Explorer right-click commands for instant analysis.

- **Tree Views & Sidebar Explorers**:
  - **Repository Explorer**: Browse files, layers, active workspace context.
  - **Knowledge Graph**: Interactive symbol & entity node hierarchy.
  - **Architecture Layers**: View 9 architecture layers & clean hexagonal boundaries.
  - **Learning Journey**: Mastery progress and educational exercises.
  - **Bookmarks & Recent Conversations**: Instant access to pinned entities.

- **Webview Panels**:
  - **Diagram Panel**: Interactive Mermaid component & sequence diagrams.
  - **Call Graph Panel**: Interactive canvas graph for tracing caller/callee trees and blast radius.
  - **Architecture View**: Layer inspection and pattern audits.

- **Editor Sync & Offline Mode**:
  - Automatically syncs active editor file with repository context.
  - Gracefully detects backend availability and recovers automatically when backend comes online.

---

## 3. Supported Commands & Command Palette

| Command | Title | Action |
|---|---|---|
| `repoIntelligence.explainCurrentFile` | `Repository: Explain Current File` | Explains architecture & purpose of active file |
| `repoIntelligence.traceCurrentFunction` | `Repository: Trace Execution` | Traces call sequence and execution flow |
| `repoIntelligence.reviewCurrentFile` | `Repository: Review Repository` | Evaluates ArchUnit rules and code health |
| `repoIntelligence.generateDocumentation` | `Repository: Generate Documentation` | Generates documentation & ADRs |
| `repoIntelligence.generateDiagram` | `Repository: Generate Diagram` | Renders Mermaid sequence & architecture diagrams |
| `repoIntelligence.architectureOverview` | `Repository: Architecture Overview` | Inspects 9 architectural layers & patterns |
| `repoIntelligence.searchRepository` | `Repository: Search Knowledge Graph` | Performs universal semantic entity search |
| `repoIntelligence.impactAnalysis` | `Repository: Impact Analysis` | Calculates change blast radius & consumer risk |
| `repoIntelligence.learningJourney` | `Repository: Start Learning Journey` | Guides interactive repository learning pathway |
| `repoIntelligence.openRepositoryGraph` | `Repository: Open Repository Graph` | Opens interactive Knowledge Graph panel |
| `repoIntelligence.openCallGraph` | `Repository: Open Call Graph` | Opens interactive Call Graph panel |

---

## 4. Configuration Settings

Settings can be customized in VS Code Settings (`Ctrl+,` or `Cmd+,` under `ARIA`):

| Setting | Default | Description |
|---|---|---|
| `repoIntelligence.backendUrl` | `http://127.0.0.1:8001` | URL of the Repository Intelligence Backend |
| `repoIntelligence.apiToken` | `""` | Optional API token for authenticating with the backend |
| `repoIntelligence.theme` | `"auto"` | Color theme for webview panels (`auto`, `dark`, `light`) |
| `repoIntelligence.streaming` | `true` | Enable Server-Sent Events (SSE) streaming for responses |
| `repoIntelligence.autoSync` | `true` | Automatically sync workspace context on active editor change |
| `repoIntelligence.evidenceDisplay` | `true` | Render Evidence First cards in chat |
| `repoIntelligence.codeLens.enabled` | `true` | Show CodeLens actions above functions and classes |
| `repoIntelligence.hover.enabled` | `true` | Enable symbol hover cards in code editor |

---

## 5. Performance Targets & Benchmarks

- **Extension Activation**: `< 500 ms`
- **Sidebar Loading**: `< 1 second`
- **Streaming Response**: Continuous SSE streaming
- **Editor Selection Sync**: Instant (`< 50 ms`)

---

## 6. Troubleshooting

- **Backend Offline Warning**: Ensure the backend server is running (`uvicorn backend.api:app --port 8001`). Click **Connect to Backend** in the sidebar.
- **CodeLens Not Visible**: Verify `repoIntelligence.codeLens.enabled` is set to `true` in VS Code settings.
- **Graph Render Issues**: Click the **Refresh** button in the Webview panel toolbar to re-fetch graph data.

---

## 7. Development & Contribution Guide

### Prerequisites
- Node.js `^20.0.0`
- VS Code `^1.85.0`
- TypeScript `^5.3.3`

### Building & Packaging
```bash
cd vscode-extension
npm install
npm run compile
npx vsce package
```
