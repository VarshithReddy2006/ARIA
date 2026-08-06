# Installation & Setup Guide — Repo Intelligence Agent v1.5.0

This guide walks you through setting up and running the Repo Intelligence Agent backend, frontend, VS Code extension, and Docker containers.

---

## Prerequisites

Ensure you have the following tools installed:

- **Python**: Version `>=3.9` (fully validated against Python `3.10`, `3.11`, and `3.12` in development).
- **Node.js**: Version `18` or higher (LTS recommended) for compiling the Astro frontend and VS Code extension.
- **npm**: Version `9.x` or `10.x`.
- **Git**: Required for cloning the repositories to analyze.
- **Docker & Compose**: (Optional) For running the application in containers.

---

## 1. Environment Variable Configuration

Create a `.env` file in the root directory. You can copy the template:

```bash
cp .env.example .env
```

Open the `.env` file and configure the settings:

```env
# ── Application Environment ──────────────────────────────────────────────────
APP_ENV=development
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8001
LOG_LEVEL=INFO
LOG_FORMAT=human  # or "json" in production

# ── LLM Orchestration ────────────────────────────────────────────────────────
# Default provider (gemini or deepseek)
LLM_PROVIDER=gemini

# Google Gemini API key
GEMINI_API_KEY=your_google_ai_studio_api_key
GEMINI_MODEL=gemini-2.5-flash

# NVIDIA NIM DeepSeek configuration (failover or primary)
DEEPSEEK_API_KEY=your_nvidia_nim_api_key
DEEPSEEK_BASE_URL=https://integrate.api.nvidia.com/v1
DEEPSEEK_MODEL=deepseek-ai/deepseek-v4-flash

# ── Ingestion & In-Memory Store ──────────────────────────────────────────────
# Personal Access Token (PAT) recommended to avoid rate limits when cloning
GITHUB_TOKEN=your_github_personal_access_token

# Storage paths
SQLITE_DB_PATH=data/repo_understanding.db
CHROMA_DB_PATH=data/chroma_db
CACHE_FILE_PATH=data/cache.json
CLONED_REPOS_PATH=data/cloned_repos

# ── Security & Authentication ────────────────────────────────────────────────
# Rate limiting (0 = disabled)
RATE_LIMIT_PER_MINUTE=60
# Optional API key authentication (leave blank to disable in development)
# API_KEY=your_secret_api_key_here

# ── Frontend & CORS ──────────────────────────────────────────────────────────
FRONTEND_URL=http://localhost:4321
```

---

## 2. Backend Installation & Startup

### Step A: Initialize Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\activate
```
On Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step B: Install Packages
Install the backend dependencies and the command-line interface in editable mode:
```bash
pip install -e .
```

### Step C: Verify Ingestion Engine CLI
```bash
repo-intel --help
```

### Step D: Run the FastAPI Server
```bash
python backend/main.py
```
- **REST Interactive Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **Health Endpoint**: [http://localhost:8001/health](http://localhost:8001/health)

---

## 3. Frontend Installation & Startup

The frontend is an Astro 4 web application using React.

### Step A: Install Node Dependencies
```bash
cd frontend
npm install
```

### Step B: Start Dev Server
```bash
npm run dev
```
- **Web Application Portal**: [http://localhost:4321](http://localhost:4321)
- **Compile Production Bundle**: `npm run build`
- **Lint Check**: `npm run lint`

---

## 4. VS Code Extension Installation

The extension brings codebase intelligence highlights (symbol hovers, CodeLenses, graphs, and chat) directly into your editor.

### Step A: Compile the Extension
```bash
cd vscode-extension
npm install
npm run compile
```

### Step B: Install the Extension to VS Code
1. Open the `/vscode-extension` directory in VS Code.
2. Press `F5` to open a new **Extension Development Host** window.
3. To package the extension as a `.vsix` file:
   ```bash
   npx @vscode/vsce package --allow-missing-repository
   ```
4. Install the packaged `repo-intelligence-agent-0.1.0.vsix` file using VS Code's **Install from VSIX...** option.

---

## 5. Docker Setup (Alternative Launch)

Run the entire suite (FastAPI backend + Astro frontend) inside a multi-container environment.

### Run in Development Mode
Mounts local directories for hot-reloads:
```bash
docker-compose -f docker-compose.dev.yml up --build
```

### Run in Production Mode
Packages compiled static assets:
```bash
docker-compose -f docker-compose.prod.yml up --build
```

---

## 6. Verification Checklist

To confirm your installation is 100% stable, execute this check:
```bash
# 1. Run backend tests
pytest tests/

# 2. Check Python code styling
ruff check .

# 3. Check Frontend type compliance
cd frontend
npm run lint
```
All should complete with **zero errors**.
