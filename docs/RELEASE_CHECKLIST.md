# Release Readiness Checklist — v1.5.0

Use this checklist to verify that all components are verified and release-ready before promoting to a production release.

---

## 1. Backend Verification

- [ ] **Startup and Configuration**: Confirm that the backend starts with `python -m uvicorn backend.api:app` without crashing.
- [ ] **Environment Validation**: Confirm all API keys (`GEMINI_API_KEY`, `DEEPSEEK_API_KEY`) validate successfully at startup.
- [ ] **Database Migrations**: Run `python -m backend.cli run-migrations` on a fresh SQLite database file and confirm schema setup.
- [ ] **Persistence**: Confirm inspection, advisor, and execution reports are written to disk under `data/`.
- [ ] **REST API endpoints**: Verify all REST endpoints respond with correct Pydantic models.

---

## 2. VS Code Extension Verification

- [ ] **Compilation**: Compile successfully using `npm run compile` with zero errors.
- [ ] **Extension Activation**: Verify that opening a workspace folder activates the extension.
- [ ] **Status Bar**: Confirm that the status bar item displays the active repository and connection status.
- [ ] **Commands**: Check that Command Palette triggers (`repoIntelligence.setActiveRepository`, `repoIntelligence.showCallGraph`) execute.
- [ ] **Webview Panels**: Confirm interactive dependency graphs and call graphs render correctly.

---

## 3. Packaging & Installation

- [ ] **License Check**: Confirm `LICENSE` file is copied to `vscode-extension/LICENSE`.
- [ ] **VSIX Build**: Run `npx @vscode/vsce package --allow-missing-repository` inside `vscode-extension` and verify a `.vsix` is produced without errors or warnings.
- [ ] **Clean Profile Test**: Install the built VSIX on a clean VS Code profile (`code --user-data-dir ...`) and confirm activation.

---

## 4. Test Suite Verification

- [ ] **Backend Tests**: Run `pytest tests/` and verify that all **794 automated tests** pass.
- [ ] **Extension Tests**: Run `npm test` inside `vscode-extension` and verify all **110 automated tests** pass.
- [ ] **Regression Coverage**: Confirm that tests protect against digital twin schema mismatches (RIVSC-200, RIVSC-201).

---

## 5. Documentation Review

- [ ] **README**: Verify the root `README.md` includes correct quickstart commands.
- [ ] **Execution Guide**: Verify that `docs/EXECUTION_GUIDE.md` is complete and clear.
- [ ] **Changelog**: Confirm `CHANGELOG.md` lists the current release (`[1.5.0]`).

---

## 6. Performance Benchmarks

- [ ] **Analysis Latency**: Confirm repository ingestion and twin construction takes less than 5 seconds.
- [ ] **Inspection Time**: Verify `elapsed_ms` in the inspection report is under 500ms.
- [ ] **UI Responsiveness**: Confirm tree view expansion and hover documentation display under 100ms.

---

## 7. Known Limitations

- *Windows File Paths*: Large repositories on Windows may encounter slower git clone and parse speeds due to I/O constraints.
- *LLM Rate Limits*: High-frequency chat queries may trigger token rate limiters from the LLM provider.

---

## 8. Manual Validation Sequence

1. Launch backend server.
2. Package and install VSIX on a clean VS Code profile.
3. Open a target repository folder.
4. Run "Set Active Repository" to `owner/repo-name`.
5. Run "Analyze Repository".
6. Expand "Engineering Findings", "Advisor Dashboard", and "Execution Planner" views.
7. Verify symbol hovers and CodeLens trigger correctly.

---

## 9. Release Automation & Publishing

- [ ] **Version Tagging**: Create a git tag for the release:
  ```bash
  git tag -a v1.5.0 -m "Release v1.5.0 - Production Release"
  git push origin v1.5.0
  ```
- [ ] **GitHub Release**: Draft a new release on GitHub, attaching `repo-intelligence-agent-0.1.0.vsix` as a binary asset.
- [ ] **Marketplace Publication**: Publish the VSIX to the VS Code Marketplace:
  ```bash
  vsce publish -p <token>
  ```
