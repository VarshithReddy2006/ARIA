# Development Setup & Contributor Guide — ARIA v1.5.0

This document covers local environment setup, running backend and frontend services, and testing.

---

## Prerequisites

- **Python**: Version `>=3.9` (fully validated against `3.10`, `3.11`, and `3.12` in development)
- **Node.js**: 18 or newer (LTS recommended)
- **Git**: Required for cloning analyzed repositories
- **LLM API key**: Either a Google AI Studio key (`GEMINI_API_KEY`) or an NVIDIA NIM key (`DEEPSEEK_API_KEY`). Gemini is the default provider.
- **Disk space**: At least 2 GB for the `BAAI/bge-small-en-v1.5` embedding model cache

---

## Backend Setup

### 1. Clone the project

```bash
git clone https://github.com/VarshithReddy2006/Repo-Intelligence-Agent.git
cd Repo-Intelligence-Agent
```

### 2. Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e .
```

This installs the package in editable mode and registers the `repo-intel` CLI script.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials. Minimum required:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_google_ai_studio_api_key

# Or use DeepSeek instead:
# LLM_PROVIDER=deepseek
# DEEPSEEK_API_KEY=your_nvidia_nim_api_key

GITHUB_TOKEN=your_github_pat   # Recommended; raises clone rate limit

# Important: set this outside the project tree to avoid uvicorn reload loops
CLONED_REPOS_PATH=C:/repo_intelligence_storage/cloned_repos
```

See [Configuration](../README.md#configuration) in the README for the full variable reference.

### 5. Start the backend server

```bash
python backend/main.py
```

This starts uvicorn on port **8001** with hot-reload in development mode. The reload watcher is filtered to `backend/`, `services/`, `agents/`, `memory/`, and `models/` — it excludes `data/`, `__pycache__/`, and `tests/` to prevent reload loops.

- Interactive API docs: `http://localhost:8001/docs`
- Health check: `http://localhost:8001/health`

---

## Frontend Setup

The frontend is an Astro 4 application with React components.

### 1. Install packages

```bash
cd frontend
npm install
```

### 2. Start the dev server

```bash
npm run dev
```

Open `http://localhost:4321` in your browser.

The frontend defaults to `http://localhost:8001` as the API base URL. Check `frontend/.env` if you need to change this (`PUBLIC_API_URL=http://localhost:8001`).

---

## Running Tests

```bash
pytest tests/ -v
```

> Always target `pytest tests/` explicitly. Running `pytest` from the project root without a path causes it to traverse `data/` and collect import errors from cloned repositories.

```bash
# With coverage
pytest tests/ --cov=. --cov-report=term-missing

# Single test file
pytest tests/test_chat.py -v
```

All tests mock LLM calls and GitHub API calls — no API quota is consumed.

---

## Linting and Formatting

```bash
# Check and auto-fix
ruff check --fix .

# Format
ruff format .

# Check without fixing (CI mode)
ruff check .
ruff format --check .
```

---

## Troubleshooting Setup

**BGE model download hangs on first start**

Pre-download the model manually:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```

**ChromaDB dimension mismatch error**

Delete the vector store and re-analyze:
```powershell
# Windows
Remove-Item -Recurse -Force data/chroma_db
```
```bash
# macOS / Linux
rm -rf data/chroma_db
```

**Uvicorn keeps reloading during analysis**

Set `CLONED_REPOS_PATH` to a path outside the project directory. Without this, WatchFiles detects new files being written to `data/` and triggers a reload during analysis.

**Provider validation fails at startup**

Check the startup log for `LLM_PROVIDER_HEALTH healthy=false`. The error message includes the `error_type` (e.g., `invalid_credential_type`, `missing_credential`) and a `recommendation` field. The most common cause is using an OAuth token instead of a Google AI Studio Developer API key.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more issues.
