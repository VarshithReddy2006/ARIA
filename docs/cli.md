# CLI Guide

The ARIA platform includes a first-party command-line interface (`repo-intel`) built using **Typer**.

The CLI communicates directly with the FastAPI server via HTTP and does not replicate database or LLM service bindings locally, keeping execution lightweight.

## Installation

Ensure your virtual environment is active, then install the package in editable mode to register the console script:
```bash
pip install -e .
```

---

## Commands

### 1. `repo-intel version`
Prints the CLI version and queries the status of the remote API.
```bash
repo-intel version
```

### 2. `repo-intel health`
Performs connection and subsystem health checks (database, cache, vector store, etc.).
```bash
repo-intel health --url http://localhost:8001
```

### 3. `repo-intel analyze`
Triggers full or incremental analysis of a GitHub repository and streams progress updates.
```bash
repo-intel analyze https://github.com/fastapi/fastapi --branch master --url http://localhost:8001
```

### 4. `repo-intel graph`
Retrieves React-Flow compatible module dependency structure logs for the specified repository.
```bash
repo-intel graph fastapi fastapi
```

### 5. `repo-intel call-graph`
Queries call hierarchy indexes for the specified repository.
```bash
repo-intel call-graph fastapi fastapi
```

### 6. `repo-intel api-surface`
Retrieves API surface descriptions, visibility summaries, and exported classifications.
```bash
repo-intel api-surface fastapi fastapi
```

### 7. `repo-intel report`
Generates and downloads the Repository Intelligence Report for a given repository.
```bash
# Generate and download default HTML report
repo-intel report fastapi/fastapi

# Generate and download Markdown report
repo-intel report fastapi/fastapi --markdown

# Generate and download PDF-friendly HTML report to a specific path
repo-intel report fastapi/fastapi --pdf -o reports/fastapi_audit.html
```

### 8. `repo-intel mcp`
Launches the Model Context Protocol (MCP) server over `stdio` transport.
```bash
repo-intel mcp
```

---

## Model Context Protocol (MCP) Integration

Exposing ARIA as an MCP server allows external LLM clients (such as **Claude Desktop** or **Cursor**) to query symbol indexes, call graphs, and run search queries directly.

### Claude Desktop Configuration

To register ARIA with Claude Desktop, add the following to your `claude_desktop_config.json` (typically located at `%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

**Using Gemini (default provider):**
```json
{
  "mcpServers": {
    "repo-intelligence": {
      "command": "repo-intel",
      "args": ["mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "your_google_ai_studio_key"
      }
    }
  }
}
```

**Using DeepSeek via NVIDIA NIM:**
```json
{
  "mcpServers": {
    "repo-intelligence": {
      "command": "repo-intel",
      "args": ["mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "your_nvidia_nim_key"
      }
    }
  }
}
```

If you prefer to run the CLI directly via Python rather than the global executable, use:

```json
{
  "mcpServers": {
    "repo-intelligence": {
      "command": "python",
      "args": ["-m", "backend.cli", "mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token_here",
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "your_google_ai_studio_key"
      }
    }
  }
}
```

> [!NOTE]
> Ensure the Python executable used is in the virtual environment where `repo-intelligence-agent` is installed (e.g. `C:\path\to\project\.venv\Scripts\python.exe` on Windows).

