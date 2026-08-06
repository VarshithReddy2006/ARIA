# Repository AI Copilot V1 (Iteration 12)

## Overview

**Iteration 12** introduces the **Repository AI Copilot** — an intelligent engineering assistant that reasons over the Repository Knowledge Graph, Workspace State, and deterministic intelligence engines without hallucinating repository structure.

---

## Architecture & Subsystems Implemented

### 1. Backend Copilot Engine (`backend/copilot/`)
- **`tool_registry.py`**: Central registry exposing 15 deterministic tools (`query_knowledge_graph`, `get_node_architecture`, `get_call_graph`, `get_impact_analysis`, `get_rule_violations`, `get_learning_step`, `get_execution_scenario`, `get_quality_score`).
- **`copilot_tools.py`**: Execution handlers connecting existing analysis services.
- **`copilot_context.py`**: Context builder aggregating selected file, active intent, workspace mode, context state, layer, metrics, and pinned items.
- **`copilot_prompt_builder.py`**: Grounded system prompt builder instructing LLMs to reason over deterministic evidence.
- **`copilot_memory.py` & `conversation_manager.py`**: Session turn logging and entity memory.
- **`copilot_reasoning.py`**: Multi-step reasoning orchestrator.
- **`copilot_response.py`**: Formats grounded response payloads with evidence cards, citations, and follow-up suggestions.
- **`copilot_stream.py`**: SSE streaming response generator with progress indicators.
- **`copilot_controller.py`**: Main copilot controller.
- **`copilot_router.py`**: FastAPI router exposing `/api/copilot/chat`, `/api/copilot/history`, `/api/copilot/commands`, `/api/copilot/tools`.

### 2. Copilot Slash Commands (13 Commands)
- `/explain`, `/trace`, `/compare`, `/learn`, `/debug`, `/review`, `/document`, `/diagram`, `/impact`, `/architecture`, `/security`, `/performance`, `/search`.

### 3. Frontend Copilot Workstation (`frontend/src/components/copilot/`)
- **`CopilotWorkstation.tsx`**: 3-Column AI Copilot interface:
  - *Left*: Session Conversation History list.
  - *Center*: Streaming Chat, expandable Evidence Cards, Reasoning Progress indicators, slash command auto-complete.
  - *Right*: Active Workspace Context Drawer (Current File, Intent, Layer, Pinned Items, Knowledge Graph Nodes).
  - *Bottom Bar*: Quick Actions (`Explain`, `Trace`, `Compare`, `Summarize`, `Generate Diagram`, `Generate ADR`).
- **`EvidenceCard.tsx`**: Displays cited repository entities, layers, execution paths, metrics, and rules.
- **`ReasoningProgress.tsx`**: Animated tool execution and reasoning indicators.
- **`CopilotContextBar.tsx`**: Active workspace context drawer.
