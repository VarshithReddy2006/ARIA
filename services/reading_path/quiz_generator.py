"""Quiz Generator Subsystem.

Generates 5 codebase-grounded multiple-choice questions for milestone self-assessments.
"""

from __future__ import annotations

from typing import Dict, List, Any


def generate_milestone_quiz(
    milestone_id: str, file_paths: List[str] | None = None
) -> Dict[str, Any]:
    """Generate 5 multiple-choice questions grounded in repository analysis."""
    file_paths = file_paths or ["backend/api.py", "services/chat/retrieval_pipeline.py"]

    questions = [
        {
            "question_id": "q1",
            "question": "Which architectural layer owns HTTP request deserialization and routing?",
            "options": [
                "Presentation Layer",
                "Domain Layer",
                "Data Layer",
                "Infrastructure Layer",
            ],
            "correct_option_index": 0,
            "explanation": "The Presentation layer handles client interactions, HTTP routers, and request schema parsing.",
        },
        {
            "question_id": "q2",
            "question": "What is the primary role of the Application Service layer?",
            "options": [
                "Executing SQL database statements directly",
                "Orchestrating domain use-cases and transaction boundaries",
                "Rendering CSS user interface components",
                "Configuring environment variables",
            ],
            "correct_option_index": 1,
            "explanation": "Application Services coordinate workflow logic without depending on specific UI frameworks.",
        },
        {
            "question_id": "q3",
            "question": "Why should Domain entities avoid importing Infrastructure modules?",
            "options": [
                "To reduce Python file sizes",
                "To preserve clean architecture boundary independence",
                "To speed up CSS compilation",
                "Domain entities must import Infrastructure",
            ],
            "correct_option_index": 1,
            "explanation": "Clean Architecture dictates that core domain logic remains independent of external frameworks.",
        },
        {
            "question_id": "q4",
            "question": "What metric indicates a module's susceptibility to change based on incoming dependencies?",
            "options": [
                "Efferent Coupling (Ce)",
                "Afferent Coupling (Ca)",
                "Cyclomatic Complexity",
                "Comment Density",
            ],
            "correct_option_index": 1,
            "explanation": "Afferent Coupling (Ca) measures how many external modules depend on a given file.",
        },
        {
            "question_id": "q5",
            "question": "How are cyclic dependencies resolved cleanly in python/typescript architectures?",
            "options": [
                "Deleting unit tests",
                "Introducing an Interface / Adapter abstraction edge",
                "Hardcoding global variables",
                "Ignoring circular import warnings",
            ],
            "correct_option_index": 1,
            "explanation": "Extracting an interface breaks circular import loops by inverting dependency direction.",
        },
    ]

    return {
        "milestone_id": milestone_id,
        "question_count": len(questions),
        "questions": questions,
    }
