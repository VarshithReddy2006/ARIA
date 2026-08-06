"""CI Guard Test for AI Integrity (Recovery Item R-006).

Asserts that no module under services/ or backend/ returns hardcoded fabricated
confidence literals (such as "confidence": 0.97 or "Confidence: 95%").
Fails automatically if a hardcoded fabricated confidence literal is reintroduced.
"""

import ast
import os
import pytest


FORBIDDEN_CONFIDENCE_LITERALS = {0.97, 95}


def test_no_hardcoded_fabricated_confidence_literals_in_backend_or_services():
    """AST-scan backend/ and services/ to ensure no hardcoded fake confidence literals exist."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dirs = [
        os.path.join(root_dir, "backend"),
        os.path.join(root_dir, "services"),
    ]

    violations = []

    for target_dir in target_dirs:
        for dirpath, _, filenames in os.walk(target_dir):
            if "__pycache__" in dirpath:
                continue
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                file_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(file_path, root_dir)

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Check string literal formatting (e.g. "Confidence: 95%")
                if "Confidence: 95%" in content or "confidence: 0.97" in content:
                    violations.append((rel_path, "Contains forbidden hardcoded confidence string literal"))

                # AST analysis for dictionary keys or kwargs
                try:
                    tree = ast.parse(content, filename=file_path)
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    # Check Dict keys: {"confidence": 0.97} or {"confidence": 95}
                    if isinstance(node, ast.Dict):
                        for k, v in zip(node.keys, node.values):
                            if isinstance(k, ast.Constant) and str(k.value).lower() in ("confidence", "topic_confidence"):
                                if isinstance(v, ast.Constant) and v.value in FORBIDDEN_CONFIDENCE_LITERALS:
                                    violations.append(
                                        (rel_path, f"Line {node.lineno}: Dict key '{k.value}' assigned forbidden literal {v.value}")
                                    )

    assert (
        len(violations) == 0
    ), f"AI Integrity Guard Violation(s) detected:\n" + "\n".join(f"  {path}: {reason}" for path, reason in violations)
