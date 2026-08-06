# Repository Intelligence Platform — End-to-End Execution Guide

This guide describes how to set up, build, package, run, and validate the Repository Intelligence Platform from scratch.

---

## 1. Prerequisites

Before setting up the platform, ensure your environment meets the following specifications:

- **OS**: Windows, macOS, or Linux (Ubuntu 20.04+)
- **Python**: Version `>=3.9` (validated against Python `3.10`, `3.11`, and `3.12` in development)
- **Node.js**: Version `18` or higher (LTS recommended)
- **npm**: Version `9.x` or `10.x`
- **VS Code**: `v1.85.0` or higher
- **Git**: Version `2.30.0` or higher (installed and configured in your PATH)

---

## 2. Backend Setup

Follow these steps to configure and start the backend service.

### Step 2.1: Create a Virtual Environment & Install Dependencies
Run these commands from the repository root:
```bash
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Upgrade pip and install package dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2.2: Configure Environment Variables
Copy the template `.env.example` to `.env` and fill in the required LLM provider credentials:
```bash
# On Windows:
copy .env.example .env
# On macOS/Linux:
cp .env.example .env
```
Ensure your `.env` contains the required keys:
```env
PORT=8001
HOST=127.0.0.1
GEMINI_API_KEY=your_gemini_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### Step 2.3: Run Database Migrations
Initialize the local SQLite database state:
```bash
python -m backend.cli run-migrations
```

### Step 2.4: Start the FastAPI Backend Server
Launch the development server:
```bash
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8001 --reload
```

---

## 3. VS Code Extension Setup

Follow these steps to compile and package the extension.

### Step 3.1: Install Node Dependencies
Navigate to the `vscode-extension` directory and install the packages:
```bash
cd vscode-extension
npm install
```

### Step 3.2: Compile and Package the Extension
Compile TypeScript files and create the `.vsix` distribution package:
```bash
# Compile TypeScript code
npm run compile

# Package the extension into a VSIX file
npx @vscode/vsce package --allow-missing-repository
```
This generates the packaged file: `vscode-extension/repo-intelligence-agent-0.1.0.vsix`.

---

## 4. VSIX Installation

Verify the extension in a clean, isolated VS Code profile:

1. Open your terminal.
2. Create a clean profile directory:
   ```bash
   mkdir -p C:\temp\vscode-profile
   ```
3. Launch a new VS Code window using that profile:
   ```bash
   code --user-data-dir C:\temp\vscode-profile\data --extensions-dir C:\temp\vscode-profile\extensions
   ```
4. In the new VS Code window:
   - Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`).
   - Select **Extensions: Install from VSIX...**.
   - Locate and select `repo-intelligence-agent-0.1.0.vsix`.
   - Click **Install**.
5. Once installation finishes, reload the window (`Developer: Reload Window`).
6. Open your target repository folder in VS Code.

---

## 5. End-to-End Functional Verification

Confirm all components function correctly by completing the following checklist.

### Feature Checklist

- **[ ] Backend health**: Open a browser or run `curl http://127.0.0.1:8001/health` and verify the status is `"healthy"`.
- **[ ] Analyze Repository**: Click **Repo Intelligence: Analyze Repository** in the VS Code sidebar. Verify that the repository is cloned and the Digital Twin / Knowledge Graph are built under `data/`.
- **[ ] Findings**: Verify that the **Engineering Findings** panel renders the list of detected issues (Complexity, Performance, etc.).
- **[ ] Advisor**: Verify that the **Advisor Dashboard** lists advisor recommendations and roadmaps.
- **[ ] Execution Planner**: Verify that the **Execution Planner** displays tasks, batches, critical paths, and rollback checkpoints.
- **[ ] Hover**: Open a file, hover over a symbol (function/class name), and verify that the rich documentation card appears.
- **[ ] CodeLens**: Verify that CodeLens annotations ("Show Callers", "Show Blast Radius") render above symbol declarations.
- **[ ] Code Actions**: Highlight a block of code, press `Ctrl+.` / `Cmd+.`, and verify that refactoring suggestions are shown.
- **[ ] Search**: Use the **Search** field in the Repo Intelligence bar and verify that it resolves matching files/symbols.
- **[ ] Review**: Right-click a file in the explorer, select **Repo Intelligence: Review Current File**, and check for feedback.
- **[ ] Graph Navigation**: Select **Show Call Graph** or **Show Dependency Graph** to display interactive visual maps.

---

## 6. Troubleshooting

### Issue 6.1: Backend is unavailable
- **Symptoms**: The Backend Connection tree view shows status "offline".
- **Probable Cause**: The FastAPI server is not running, or is running on a different port/address.
- **Resolution**: Ensure you ran `python -m uvicorn backend.api:app --host 127.0.0.1 --port 8001`. Check if `repoIntelligence.backendUrl` in VS Code settings matches `http://127.0.0.1:8001`.

### Issue 6.2: VSIX packaging failure
- **Symptoms**: `vsce package` errors out complaining about missing repository fields or missing files.
- **Probable Cause**: Repository metadata is missing from `package.json`, or the `LICENSE` file is missing.
- **Resolution**: Run `npx @vscode/vsce package --allow-missing-repository`. Ensure a copy of the `LICENSE` file exists in the `vscode-extension` directory.

### Issue 6.3: Empty Tree Views
- **Symptoms**: The findings, advisor, or execution panels show "No active repository" or are completely blank.
- **Probable Cause**: Active repository is not selected, or analysis hasn't been run yet.
- **Resolution**: Click **Set Active Repository** (or run command `repoIntelligence.setActiveRepository`) and enter `owner/repo-name`. Run **Analyze Repository** to kick off the backend pipeline.

### Issue 6.4: Authentication/Access Token Errors
- **Symptoms**: Analysis fails with a 401 or 403 status code.
- **Probable Cause**: Required GitHub token or API Key is missing or invalid.
- **Resolution**: Ensure `repoIntelligence.apiToken` is set in your VS Code settings, or check your backend `.env` variables.

### Issue 6.5: API Endpoint mismatch (404 Not Found)
- **Symptoms**: Generating an execution plan returns a 404 error from the server.
- **Probable Cause**: VS Code extension client calls the wrong API path (e.g. `/execution` instead of `/execution-plan`).
- **Resolution**: Ensure you are using v1.5.0 where the client path has been mapped to `/execution-plan`.
