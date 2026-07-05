# Manual Verification Protocol: Impact Analysis Visualization (Phase 3C)

This document outlines the step-by-step checklist to manually test and verify the **Impact Analysis Graph** visual layer.

---

## 1. Setup
Ensure the Python backend is running on port 8001 and the Astro frontend is running on port 4321. Navigate to the dashboard (e.g. `http://localhost:4321/?repo=Repo-Intelligence-Agent`).

---

## 2. Validation Checklist

### Test Case 1: Tab Integration & Deferral (Lazy Loading)
- [ ] **Action**: Switch tabs. Verify **Impact Analysis** is situated as the 4th tab between Reading Path and Issue Intelligence.
- [ ] **Observe**: Clicking the tab shows the input query runner panel instead of immediately calling the API.
- [ ] **Observe**: Verify that the API endpoint `POST /api/impact-analysis` is NOT called until a preset is clicked or the form is submitted (lazy loading verified).

### Test Case 2: Scenario Presets & Input
- [ ] **Action**: Click the quick preset `"Add GitHub OAuth Login"`.
- [ ] **Observe**: The textarea is populated with the text `"Add GitHub OAuth Login"`.
- [ ] **Observe**: A loading overlay appears immediately with the text `"Analyzing Change Impact..."`.
- [ ] **Observe**: Look at the network log and verify a request to `POST /api/impact-analysis` is sent with:
  ```json
  {
    "repo": "Repo-Intelligence-Agent",
    "issue": "Add GitHub OAuth Login"
  }
  ```

### Test Case 3: Risk Intelligence & Summary Panel
- [ ] **Observe**: The left side displays the **Risk Intelligence** summary:
  - Shows the risk level (e.g. `HIGH RISK` inside a red-themed alert box).
  - Shows analysis confidence percentage (e.g. `95% certainty score`).
  - Shows correct count of estimated impacted files (e.g., `14 files` or matches).
  - Lists the affected component labels as purple badges (e.g. `API Layer`, `Services`).
- [ ] **Observe**: The **Propagation Overview** box displays correct breakdown:
  - Count of directly affected files (matching the red nodes).
  - Count of indirectly affected files (matching the yellow nodes).

### Test Case 4: React Flow Dependency Graph
- [ ] **Observe**: The graph renders correctly with Left-to-Right auto-layout (Dagre LR layout).
- [ ] **Observe**: Nodes are colored correctly:
  - Directly affected files (`backend/api.py`, `services/github_service.py`) are rendered in red with borders.
  - Indirectly affected files (`tests/test_api.py`, etc.) are rendered in yellow.
  - Component nodes (`API Layer`, `Services`) are rendered in purple.
- [ ] **Observe**: Solid red edges represent direct propagation paths.
- [ ] **Observe**: Dotted purple edges represent mapping links from Component nodes to their related files.
- [ ] **Observe**: Red solid edges are animated, representing the propagation flow of change risk.

### Test Case 5: Drawer Explorer Selection
- [ ] **Action**: Click a red node (e.g., `backend/api.py`).
- [ ] **Observe**: The right side-panel slides out showing `Dependency Chain Explorer`:
  - Path identifier (e.g. `backend/api.py`).
  - Impact type is marked `direct` with a red badge.
  - Dependents and dependencies counts are calculated (e.g., 2 dependents, 3 dependencies).
  - Risk Contribution is calculated (e.g. `High`).
  - Action buttons (`Open File`, `View Architecture`, `Ask About Impact`) are rendered with icons and disabled, containing `Future` badges.
- [ ] **Action**: Click the `X` close button on the drawer.
- [ ] **Observe**: The drawer slides out of view, and the graph expands to fit the screen.
- [ ] **Action**: Click the "Reset Scenario" button in the left summary panel.
- [ ] **Observe**: The graph is cleared, and the query runner input form re-appears.

---

## 3. Codebase Verification Matrix

### Repository 1: Repo-Intelligence-Agent
- **Preset**: `"Add GitHub OAuth Login"`
- **Expected Graph Nodes**:
  - `backend/api.py` (Red / Direct)
  - `services/github_service.py` (Red / Direct)
  - `tests/*` (Yellow / Indirect)
- **Status**: PASSED.

### Repository 2: fastapi/fastapi
- **Preset**: `"Add API key authentication"`
- **Expected Graph Nodes**:
  - `fastapi/security/api_key.py` or `fastapi/security/*` (Red / Direct)
  - `fastapi/routing.py` (Red / Direct)
  - `fastapi/dependencies/utils.py` (Red / Direct)
- **Status**: PASSED.
