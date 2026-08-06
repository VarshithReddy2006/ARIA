# Installation Guide — Repo Intelligence Agent v1.5.0

This guide walks you through installing the Repo Intelligence Agent locally.

## Prerequisites

- **Python**: Version `>=3.9` (fully validated against Python `3.10`, `3.11`, and `3.12` in development).
- **Node.js**: Version `18` or higher (LTS recommended) for building the frontend.
- **Git**: Required for cloning analyzed repositories.

---

## 1. Local Python Setup

1. **Clone this repository**:
   ```bash
   git clone https://github.com/VarshithReddy2006/Repo-Intelligence-Agent.git
   cd Repo-Intelligence-Agent
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install the package in editable mode**:
   ```bash
   pip install -e .
   ```

4. **Verify CLI installation**:
   ```bash
   repo-intel --help
   ```

---

## 2. Configure Environment Variables

Create a `.env` file in the project root:
```env
# Server bindings
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8001
APP_ENV=development
LOG_LEVEL=INFO

# LLM Provider — Gemini (default) or DeepSeek
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_google_ai_studio_key

# OR use DeepSeek via NVIDIA NIM:
# LLM_PROVIDER=deepseek
# DEEPSEEK_API_KEY=your_nvidia_nim_key
# DEEPSEEK_BASE_URL=https://integrate.api.nvidia.com/v1
# DEEPSEEK_MODEL=deepseek-ai/deepseek-v4-flash

# GitHub integration
GITHUB_TOKEN=your_personal_access_token
```

---

## 3. Database & Cache Initialization

Database tables and migration schemes are automatically initialized on server boot.

To manually trigger database setup or verification:
```bash
python -c "from storage.migrations import run_migrations; run_migrations()"
```
This sets up a SQLite relational database at `data/repo_understanding.db`.
