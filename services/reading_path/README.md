# Learning Intelligence Algorithms (`services/reading_path`)

> **Status:** Intentionally Unmounted Surface (Recovery Program R-003)

---

## Overview

The modules inside `services/reading_path/` contain core learning journey, concept scoring, gap detection, dependency storytelling, architectural mentoring, and quiz generation algorithms:

* `journey_generator.py` — Generates multi-phase onboarding reading sequences.
* `concept_scorer.py` — Evaluates mastery scores over extracted codebase concepts.
* `gap_detector.py` — Identifies missing prerequisite knowledge in target repositories.
* `dependency_story.py` — Constructs narrative execution scenarios across dependencies.
* `architecture_mentor.py` — Formulates layer-by-layer architectural guidance.
* `quiz_generator.py` — Generates milestone verification quizzes.
* `progress_tracker.py` — Tracks learning progression metrics.
* `repository_knowledge_graph.py` — Graph representation for concept nodes.

---

## Unmounted Status & Recovery Rationale

In V1.0, the HTTP router (`backend/routers/reading_path.py`) evaluated these algorithms over a hardcoded `DEFAULT_REPO_FILES` fallback list rather than real repository AST analysis, producing repository-independent results.

Per **Recovery Item R-003**, the user-facing router and frontend surfaces have been removed to prevent misrepresenting repository data. The internal algorithms in this package are retained for future activation.

---

## Future Activation Prerequisites (v1.2 Target)

Before this service package can be re-mounted to production endpoints, the following prerequisites must be fulfilled:

1. **Per-Repository Concept Extraction**: Real AST & symbol graph analysis must extract concept nodes dynamically per target repository rather than relying on fallback lists.
2. **Authenticated User Identity**: A persistent user identity layer must be introduced to track individual developer mastery progress and milestone completions across sessions.
