"""Testing Inspection Pack.

Audits unit testing, coverage statistics, and missing test files.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class TestingInspector(InspectionPack):
    """Audits test file presence, framework setup, and test suite counts."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        files = context.twin.get("files", [])

        # Check for test files (e.g. files with 'test' in path)
        test_files = []
        for f in files:
            path = f if isinstance(f, str) else f.get("path", "")
            # check for test framework config or test files
            filename = path.split("/")[-1].lower()
            if "test_" in filename or "_test" in filename or "tests/" in path.lower():
                test_files.append(path)

        if not test_files:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="testing",
                    severity="high",
                    confidence=0.95,
                    title="Missing Test Suite Coverage",
                    description="No unit test files or test framework configurations detected in the repository.",
                    affected_entities=["Whole Codebase"],
                    evidence=[
                        "No test files matched standard patterns (test_*.py, *_test.py, etc.)."
                    ],
                    recommendations=[
                        "Setup a unit test framework (e.g., pytest, jest) and write core unit tests.",
                        "Establish code coverage thresholds in CI pipeline.",
                    ],
                    estimated_effort="4 hours",
                    metadata={"test_files_count": 0},
                )
            )
        elif len(test_files) < 3:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="testing",
                    severity="medium",
                    confidence=0.9,
                    title="Low Test File Coverage",
                    description="The codebase contains very few unit tests, which can increase bug regressions.",
                    affected_entities=test_files,
                    evidence=[f"Only found {len(test_files)} test files in codebase."],
                    recommendations=[
                        "Expand unit tests to cover critical services and controllers."
                    ],
                    estimated_effort="2 hours",
                    metadata={"test_files_count": len(test_files)},
                )
            )

        return findings
