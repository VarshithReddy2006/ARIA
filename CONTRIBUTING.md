# Contributing to ARIA v1.5.0

Thank you for contributing! This guide covers the repository structure, coding standards, branch naming, commit conventions, testing, and the pull request checklist.

---

## 1. Repository Structure

```text
├── backend/          # FastAPI server, routers, settings, and middlewares
│   ├── routers/      # Domain specific REST controllers (/api/v1)
│   └── settings.py   # Configuration schema (Pydantic Settings)
├── services/         # Core business logic engines
│   ├── chat/         # In-context conversational RAG pipeline (v2)
│   ├── llm/          # LLM Provider factory (Gemini / DeepSeek NIM)
│   └── report/       # Scoring and PDF/HTML report generators
├── frontend/         # Astro 4 + React single-page dashboard
├── vscode-extension/ # VS Code Extension package
├── tests/            # Pytest test suite
└── docs/             # Auxiliary documentation guides
```

---

## 2. Coding Conventions & Linters

### Python Code Style
- **Linter & Formatter**: We use **Ruff** for all Python code formatting and linting.
- **Ruff Validation**:
  ```bash
  ruff format --check .
  ruff check .
  ```
- **Configuration Access**: Always fetch environment settings via the Pydantic settings singleton:
  ```python
  from backend.settings import settings
  # Do not use direct os.environ.get() inside services!
  ```
- **Logging**: Use standard module-level logger:
  ```python
  import logging

  logger = logging.getLogger(__name__)
  ```

### TypeScript & React Code Style
- **Linter**: TypeScript checking is run before builds:
  ```bash
  cd frontend
  npm run lint  # executes: tsc --noEmit
  ```
- **Styling**: We use vanilla Tailwind CSS classes mapped around a strict 8px layout spacing system.

---

## 3. Branch Naming & Commits

### Branch Naming Conventions
- **Feature branch**: `feat/description-of-feature`
- **Bug fix branch**: `fix/bug-description`
- **Docs branch**: `docs/update-description`
- **Refactor branch**: `refactor/refactor-description`

### Commit Message Guidelines
We follow standard semantic commit guidelines:
- `feat: add circular dependency checker`
- `fix: resolve card height clipping on health report`
- `docs: update setup steps in INSTALLATION.md`
- `perf: pre-load tree-sitter parsers on server warmup`

---

## 4. Testing & Verification Checklist

Before opening a pull request, run this checklist locally:

### Step 1: Run Python Tests
```bash
pytest tests/
```
- Ensure all 794 tests pass.
- Write unit tests under the `/tests` directory for any new parsing or retrieval logic.

### Step 2: Format & Lint Python
```bash
ruff format .
ruff check --fix .
```

### Step 3: Lint & Build Frontend
```bash
cd frontend
npm run lint
npm run build
```
- Verify that the Astro static build finishes with **zero errors**.

---

## 5. Pull Request Guidelines

1. **Keep PRs focused**: Do not mix structural refactoring with new feature additions in the same branch.
2. **Sync documentation**: If you change configuration properties (in `backend/settings.py` or `.env.example`), update the variables reference in `INSTALLATION.md`.
3. **No regressions**: Verify that the production build executes cleanly before requesting code review.
