# Troubleshooting Guide — Repo Intelligence Agent v1.5.0

This guide lists common problems, root causes, and solutions for the Repo Intelligence Agent backend, frontend, and VS Code extension.

---

## 1. LLM Provider Authentication Failures

### Symptom
Startup logs contain:
```
ERROR backend.startup: LLM_PROVIDER_HEALTH provider=gemini healthy=false error_type=invalid_credential_type
```
Chat requests always fall back to the FallbackRenderer. `GET /api/v1/chat/health` returns `"authenticated": false`.

### Root Cause
The Gemini provider validates credentials at startup by listing available models. If the key is an OAuth token or Application Default Credentials instead of a Google AI Studio Developer API key, the SDK returns `401 UNAUTHENTICATED`.

### Solution
1. Get a valid API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Set `GEMINI_API_KEY=AIza...` in your `.env` (must start with `AIza`).
3. Call `POST /api/v1/chat/reload` or restart the server to reload.

For DeepSeek, verify your NVIDIA NIM key at [build.nvidia.com](https://build.nvidia.com) and set `DEEPSEEK_API_KEY=nvapi-...`.

---

## 2. HuggingFace Model Download Failures

### Symptom
On first startup, the process hangs or throws a network error during BGE model download.

### Root Cause
`SentenceTransformer` downloads `BAAI/bge-small-en-v1.5` (~130 MB) from HuggingFace on first use. Network restrictions can interrupt this.

### Solution
Pre-download the model manually with your virtual environment active:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
```
If you encounter rate limiting, set a HuggingFace access token:
```bash
# Windows PowerShell
$env:HF_TOKEN="your_huggingface_token"

# macOS / Linux
export HF_TOKEN="your_huggingface_token"
```

---

## 3. ChromaDB Dimension Mismatch

### Symptom
`POST /api/v1/analyze` raises `ValueError: Collection dimension mismatch`.

### Root Cause
The ChromaDB collection was created with a different embedding model (e.g. 768-dimensional embeddings) but the current model produces 384-dimensional BGE vectors.

### Solution
Delete the Chroma database directory and re-analyze.
**Windows (PowerShell):**
```powershell
Remove-Item -Recurse -Force data/chroma_db
```
**macOS / Linux:**
```bash
rm -rf data/chroma_db
```

---

## 4. Uvicorn Reload Loop During Ingestion

### Symptom
The backend restarts repeatedly while `POST /api/v1/analyze` is running, killing the active analysis.

### Root Cause
Uvicorn is watching the entire directory tree. When repositories are cloned to `data/cloned_repos/`, the writes trigger a reload.

### Solution
Ensure `CLONED_REPOS_PATH` is set outside the project directory in your `.env` (or use the default location which is `~/.repo_intelligence/cloned_repos`):
```env
CLONED_REPOS_PATH=C:/repo_intelligence_storage/cloned_repos
```
Check `backend/main.py` lines 8-19 to verify that `data/**` is included in `_RELOAD_EXCLUDES`.

---

## 5. SSE Stream Terminates Prematurely

### Symptom
The frontend/extension shows a connection error mid-analysis.

### Solution
Stop all Python/Uvicorn processes and restart:
**Windows (PowerShell):**
```powershell
Get-Process -Name python, uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
```
**macOS / Linux:**
```bash
pkill -f uvicorn; pkill -f "python backend"
```
Restart on port 8001:
```bash
python backend/main.py
```

---

## 6. Empty Tree Views in VS Code Extension

### Symptom
The findings, advisor, or execution panels show "No active repository" or are blank.

### Root Cause
Active repository is not selected, or analysis hasn't been run.

### Solution
1. Click **Set Active Repository** in the status bar or Command Palette and enter the `owner/repo-name`.
2. Run **Analyze Repository** in the sidebar.

---

## 7. Repairing Missing or Stale Indexes

### Symptom
A repository shows in recent lists but graph or symbol operations return 404 errors.

### Solution
Run the repair command to rebuild index artifacts:
```bash
curl -X POST http://localhost:8001/api/v1/repos/repair \
  -H "Content-Type: application/json" \
  -d '{"owner": "fastapi", "repo": "fastapi"}'
```
This will rebuild the dependency graph and symbol index on disk without re-cloning or re-embedding.
