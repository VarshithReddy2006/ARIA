# Manual Verification Protocol: Reading Path Visualization (Phase 3B)

This document describes the manual validation suite to verify the correctness, styling, responsiveness, and state persistence of the **Reading Path Timeline** component.

---

## 1. Setup & Environments
1. Run the FastAPI backend server:
   ```bash
   .venv\Scripts\python.exe backend/api.py
   ```
2. Run the frontend development server (Astro dashboard):
   ```bash
   npm run dev
   ```
3. Open the browser and navigate to the dashboard (typically `http://localhost:4321` depending on settings) with a test repository parameter, e.g. `?repo=Repo-Intelligence-Agent`.

---

## 2. Validation Test Cases

### Test Case 1: Dashboard Integration & Lazy Loading
- [ ] **Action**: Switch between tabs (Codebase Analysis, Architecture Graph, Reading Path, Issue Intelligence).
- [ ] **Observe**: The **Reading Path** tab is the third tab, situated between Architecture Graph and Issue Intelligence.
- [ ] **Observe**: When the Reading Path tab is clicked for the first time, a loading screen is displayed with the message `"Generating Reading Path..."`.
- [ ] **Observe**: Look at the browser network logs. Verify that the call to `POST /api/reading-order` is triggered **only** when clicking the Reading Path tab (lazy loading verified).

### Test Case 2: Timeline Rendering & Heuristics
- [ ] **Action**: Select the **Reading Path** tab and wait for load.
- [ ] **Observe**: The top summary panel shows correct metadata counts:
  - Recommended Files count.
  - Est. Reading Time matches the overall sum.
  - Correct counts of detected Entry Points and Core Modules.
- [ ] **Observe**: A vertical timeline is rendered showing Step 1, Step 2, Step 3, etc. connected by directional down-arrows.
- [ ] **Observe**: Each step card displays:
  - Relative file path.
  - Score badge (e.g. `Score: 158.64`).
  - Tier badge (e.g. `ENTRY POINT` in emerald, `CORE` in blue).
  - Importance level badge (e.g., `Critical` in green, `Important` in blue, `Optional` in gray).
  - Calculated estimated read time (e.g., `8 min` for score ~158).
  - Human-readable reason explanation.

### Test Case 3: Progress Tracking & Session Persistence
- [ ] **Action**: Select a few files and mark them as complete by clicking their checkboxes or circle indicators.
- [ ] **Observe**: The progress bar at the top updates immediately.
- [ ] **Observe**: The ASCII progress bar (`██████░░░░░░░`) updates to show the correct block ratio.
- [ ] **Observe**: The completion counts update (e.g. `3 / 15 Files Completed`).
- [ ] **Action**: Reload the browser page or navigate to another tab and return.
- [ ] **Observe**: All previously marked checkboxes remain completed, and the progress bar starts at the correct restoration level.
- [ ] **Action**: Open DevTools, go to **Application** -> **Local Storage** -> `http://localhost:...`
- [ ] **Observe**: The storage key `reading-path-{owner/repo}` exists, and its value is a JSON map of marked file paths (e.g. `{"backend/api.py":true}`).

### Test Case 4: File Intelligence Drawer
- [ ] **Action**: Click on any file card in the timeline.
- [ ] **Observe**: A side-drawer panel slides out from the right side.
- [ ] **Observe**: The drawer is titled `File Intelligence` and contains:
  - File name and path.
  - Importance score and read time.
  - Tier badge.
  - High-level explanation reason.
- [ ] **Observe**: Verify three action buttons are present: `Open File`, `Ask About File`, and `View Dependencies`. They are styled appropriately with icons and contain `Future` badges indicating placeholder status.
- [ ] **Action**: Click the close button `X` on the drawer.
- [ ] **Observe**: The side drawer collapses cleanly, returning the timeline to full width.

---

## 3. Repository Validation Matrices

### Repository 1: Repo-Intelligence-Agent
- Top entry points expected:
  1. `backend/api.py` (Rank 1, Entry Point, Critical)
  2. `backend/main.py` (Rank 2, Entry Point, Critical)
  3. `services/retrieval_service.py` (Core Module, Important)
  4. `agents/issue_mapper.py` (Core Module, Important)

### Repository 2: fastapi/fastapi
- Top entry points expected:
  1. `fastapi/routing.py`
  2. `fastapi/applications.py`
  3. `fastapi/__main__.py`
