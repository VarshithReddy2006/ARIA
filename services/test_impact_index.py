"""In-Memory Snapshot-Aware Test Impact Index (Phase 3, 4, 5, 6, 7).

Pre-indexes test files for a repository snapshot so that impact analysis
can query test relationships in O(1) in-memory time without re-reading or
re-parsing files from disk on every developer query.

Authoritative snapshot identity: (repo_name, commit_sha).
Thread-safe, supports incremental file updates without full rebuilds.
"""

import os
import ast
import re
import subprocess
import threading
from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from models.phase2 import EvidenceStrength


@dataclass
class TestImportFact:
    module: str
    symbol_name: str
    alias: Optional[str]
    line: int


@dataclass
class TestCallFact:
    call_repr: str
    func_name: str
    prefix: Optional[str]
    line: int


@dataclass
class TestRouteFact:
    method: str
    url: str
    line: int


@dataclass
class TestFileFacts:
    test_file: str
    mtime: float
    imports_from: List[TestImportFact] = field(default_factory=list)
    imports_module: List[Tuple[str, Optional[str], int]] = field(default_factory=list)
    calls: List[TestCallFact] = field(default_factory=list)
    routes: List[TestRouteFact] = field(default_factory=list)


def resolve_canonical_snapshot_sha(
    repo_name: str, local_path: Optional[str] = None
) -> str:
    """Resolve the canonical commit_sha identity for a repository snapshot."""
    paths_to_try = [local_path] if local_path else []
    safe_name = repo_name.replace("/", "_")
    for base in ["data/cloned_repos", "."]:
        paths_to_try.extend(
            [
                os.path.join(base, safe_name),
                os.path.join(base, safe_name.replace("VarshithReddy2006_", "")),
                os.path.join(base, repo_name),
            ]
        )

    for p in paths_to_try:
        if p and os.path.exists(os.path.join(p, ".git")):
            try:
                out = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=p,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    text=True,
                ).strip()
                if out and len(out) >= 7:
                    return out
            except Exception:
                pass

    # Check build manifest
    manifest_path = os.path.join("data", "snapshots", safe_name, "build_manifest.json")
    if os.path.exists(manifest_path):
        try:
            import json

            with open(manifest_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if "repository_hash" in data:
                    return data["repository_hash"]
        except Exception:
            pass

    return "HEAD"


class TestImpactIndex:
    """In-memory index of parsed test facts keyed by canonical snapshot identity."""

    __test__ = False
    _instances: Dict[Tuple[str, str], "TestImpactIndex"] = {}
    _lock = threading.RLock()

    def __init__(self, repo_name: str, commit_sha: str):
        self.repo_name = repo_name
        self.commit_sha = commit_sha
        self.file_facts: Dict[str, TestFileFacts] = {}
        # Inverted index: symbol_name -> Set[test_file]
        self.symbol_to_tests: Dict[str, Set[str]] = {}
        # Inverted index: module_name -> Set[test_file]
        self.module_to_tests: Dict[str, Set[str]] = {}
        # Inverted index: package_name -> Set[test_file]
        self.package_to_tests: Dict[str, Set[str]] = {}
        self._indexed = False
        self._rw_lock = threading.RLock()
        self.path_resolver: Optional[Any] = None

    @classmethod
    def get_index(
        cls, repo_name: str, commit_sha: Optional[str] = None
    ) -> "TestImpactIndex":
        sha = commit_sha or resolve_canonical_snapshot_sha(repo_name)
        key = (repo_name, sha)
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(repo_name, sha)
            return cls._instances[key]

    @classmethod
    def clear_cache(cls):
        with cls._lock:
            cls._instances.clear()

    @staticmethod
    def _is_test_file(fp: str) -> bool:
        norm = fp.lower().replace("\\", "/")
        return (
            norm.startswith("tests/")
            or "/tests/" in norm
            or norm.startswith("test/")
            or "/test/" in norm
            or os.path.basename(norm).startswith("test_")
            or os.path.basename(norm).endswith("_test.py")
            or os.path.basename(norm).endswith(".test.ts")
            or os.path.basename(norm).endswith(".test.js")
        )

    def _resolve_repo_file_path(self, file_path: str) -> Optional[str]:
        if self.path_resolver:
            try:
                res = self.path_resolver(file_path)
                if res and os.path.exists(res):
                    return res
            except Exception:
                pass
        if os.path.isabs(file_path) and os.path.exists(file_path):
            return file_path
        safe_name = self.repo_name.replace("/", "_")
        for base in ["data/cloned_repos", "."]:
            cand = os.path.join(base, safe_name, file_path)
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
            cand = os.path.join(
                base, safe_name.replace("VarshithReddy2006_", ""), file_path
            )
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
            cand = os.path.join(base, file_path)
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
        return None

    def ensure_indexed(self, test_files: List[str]):
        """Index the given test files if not already cached (thread-safe, parallel cold parse)."""
        with self._rw_lock:
            files_to_parse = []
            for tf in test_files:
                if not self._is_test_file(tf):
                    continue
                p = self._resolve_repo_file_path(tf)
                if not p or not os.path.exists(p):
                    continue

                try:
                    mtime = os.path.getmtime(p)
                except Exception:
                    continue

                existing = self.file_facts.get(tf)
                if existing and existing.mtime == mtime:
                    continue

                files_to_parse.append((tf, p, mtime))

            if not files_to_parse:
                self._indexed = True
                return

            def _parse_file(item):
                tf, p, mtime = item
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    tree = ast.parse(content, filename=p)
                    return tf, p, mtime, tree
                except Exception:
                    return tf, p, mtime, None

            from concurrent.futures import ThreadPoolExecutor

            workers = min(16, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(_parse_file, files_to_parse))

            for tf, p, mtime, tree in results:
                if tree:
                    self._populate_facts_from_tree(tf, p, mtime, tree)

            self._indexed = True

    def update_file_incremental(self, test_file: str, disk_path: Optional[str] = None):
        """Incrementally update facts for a single modified test file (Phase 7)."""
        with self._rw_lock:
            p = disk_path or self._resolve_repo_file_path(test_file)
            if not p or not os.path.exists(p):
                self.remove_file(test_file)
                return

            try:
                mtime = os.path.getmtime(p)
            except Exception:
                return

            # Remove old entries from inverted indexes
            self._remove_from_inverted(test_file)

            # Re-index single file
            self._index_single_file(test_file, p, mtime)

    def remove_file(self, test_file: str):
        """Remove a deleted test file from the index (Phase 7)."""
        with self._rw_lock:
            self._remove_from_inverted(test_file)
            self.file_facts.pop(test_file, None)

    def _remove_from_inverted(self, test_file: str):
        old_facts = self.file_facts.get(test_file)
        if not old_facts:
            return

        for imp in old_facts.imports_from:
            if imp.symbol_name in self.symbol_to_tests:
                self.symbol_to_tests[imp.symbol_name].discard(test_file)
            if imp.alias and imp.alias in self.symbol_to_tests:
                self.symbol_to_tests[imp.alias].discard(test_file)
            if imp.module in self.module_to_tests:
                self.module_to_tests[imp.module].discard(test_file)
            if "." in imp.module:
                pkg = imp.module.rsplit(".", 1)[0]
                if pkg in self.package_to_tests:
                    self.package_to_tests[pkg].discard(test_file)

        for mod_name, alias, _ in old_facts.imports_module:
            if mod_name in self.module_to_tests:
                self.module_to_tests[mod_name].discard(test_file)
            if "." in mod_name:
                pkg = mod_name.rsplit(".", 1)[0]
                if pkg in self.package_to_tests:
                    self.package_to_tests[pkg].discard(test_file)

        for call in old_facts.calls:
            if call.func_name in self.symbol_to_tests:
                self.symbol_to_tests[call.func_name].discard(test_file)

    def _index_single_file(self, test_file: str, disk_path: str, mtime: float):
        try:
            with open(disk_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
            tree = ast.parse(content, filename=disk_path)
            self._populate_facts_from_tree(test_file, disk_path, mtime, tree)
        except Exception:
            return

    def _populate_facts_from_tree(
        self, test_file: str, disk_path: str, mtime: float, tree: ast.AST
    ):
        facts = TestFileFacts(test_file=test_file, mtime=mtime)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for n in node.names:
                    alias = n.asname
                    facts.imports_from.append(
                        TestImportFact(
                            module=mod,
                            symbol_name=n.name,
                            alias=alias,
                            line=node.lineno,
                        )
                    )
                    self.symbol_to_tests.setdefault(n.name, set()).add(test_file)
                    if alias:
                        self.symbol_to_tests.setdefault(alias, set()).add(test_file)

                if mod:
                    self.module_to_tests.setdefault(mod, set()).add(test_file)
                    if "." in mod:
                        pkg = mod.rsplit(".", 1)[0]
                        self.package_to_tests.setdefault(pkg, set()).add(test_file)

            elif isinstance(node, ast.Import):
                for n in node.names:
                    alias = n.asname
                    facts.imports_module.append((n.name, alias, node.lineno))
                    self.module_to_tests.setdefault(n.name, set()).add(test_file)
                    if "." in n.name:
                        pkg = n.name.rsplit(".", 1)[0]
                        self.package_to_tests.setdefault(pkg, set()).add(test_file)

            elif isinstance(node, ast.Call):
                call_repr = ""
                func_name = ""
                prefix = None
                if isinstance(node.func, ast.Name):
                    call_repr = node.func.id
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    try:
                        call_repr = ast.unparse(node.func)
                    except Exception:
                        call_repr = getattr(node.func, "attr", "")
                    func_name = getattr(node.func, "attr", "")
                    if "." in call_repr:
                        prefix = call_repr.rsplit(".", 1)[0].split(".")[-1]

                if func_name:
                    facts.calls.append(
                        TestCallFact(
                            call_repr=call_repr,
                            func_name=func_name,
                            prefix=prefix,
                            line=node.lineno,
                        )
                    )
                    self.symbol_to_tests.setdefault(func_name, set()).add(test_file)

                if isinstance(node.func, ast.Attribute) and node.func.attr in (
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                ):
                    if (
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        url = node.args[0].value
                        facts.routes.append(
                            TestRouteFact(
                                method=node.func.attr, url=url, line=node.lineno
                            )
                        )

        self.file_facts[test_file] = facts

    def find_candidate_test_files(
        self,
        seed_files: List[str],
        target_symbols: List[str],
        api_routes: List[str],
    ) -> Set[str]:
        """Find test files that have structural touchpoints with the seeds or symbols."""
        candidates: Set[str] = set()

        # 1. Target symbols in imports or calls
        for sym in target_symbols:
            clean = sym.split(".")[-1]
            if clean in self.symbol_to_tests:
                candidates.update(self.symbol_to_tests[clean])
            # Check CamelCase to snake_case symbol matches
            snake_name = re.sub(r"(?<!^)(?=[A-Z])", "_", clean).lower()
            if snake_name in self.symbol_to_tests:
                candidates.update(self.symbol_to_tests[snake_name])

        # 2. Seed modules and packages
        for sf in seed_files:
            mod = sf.replace("/", ".").replace("\\", ".")
            if mod.endswith(".py"):
                mod = mod[:-3]
            if mod in self.module_to_tests:
                candidates.update(self.module_to_tests[mod])
            if "." in mod:
                pkg = mod.rsplit(".", 1)[0]
                if pkg in self.package_to_tests:
                    candidates.update(self.package_to_tests[pkg])
                if pkg in self.module_to_tests:
                    candidates.update(self.module_to_tests[pkg])

            # Basename module check
            base = os.path.basename(sf)
            if base.endswith(".py"):
                b_name = base[:-3]
                if b_name in self.symbol_to_tests:
                    candidates.update(self.symbol_to_tests[b_name])

        # 3. API route invocations
        if api_routes:
            for tf, facts in self.file_facts.items():
                if facts.routes:
                    for rf in facts.routes:
                        for r in api_routes:
                            clean_r = r.split()[0] if " " in r else r
                            if clean_r == rf.url or (
                                len(clean_r) > 2 and rf.url.startswith(clean_r)
                            ):
                                candidates.add(tf)
                                break

        return candidates

    def inspect_test_facts(
        self,
        test_file: str,
        seed_files: List[str],
        target_symbols: List[str],
        api_routes: List[str],
    ) -> List[Dict[str, Any]]:
        """Inspect pre-indexed test facts in-memory and generate evidence items."""
        facts = self.file_facts.get(test_file)
        if not facts:
            return []

        evidence: List[Dict[str, Any]] = []

        targets = []
        for s in target_symbols:
            if "." in s:
                parts = s.split(".")
                targets.append((parts[-2], parts[-1]))
            else:
                targets.append((None, s))

        seed_mods = set()
        seed_packages = set()
        for sf in seed_files:
            mod = sf.replace("/", ".").replace("\\", ".")
            if mod.endswith(".py"):
                mod = mod[:-3]
            seed_mods.add(mod)
            if "." in mod:
                seed_packages.add(mod.rsplit(".", 1)[0])

        aliases: Dict[str, Tuple[Optional[str], str]] = {}

        # 1. Imports from
        for imp in facts.imports_from:
            mod = imp.module
            is_seed_mod = mod in seed_mods
            is_seed_pkg = mod in seed_packages

            if is_seed_mod or is_seed_pkg:
                for parent, sym in targets:
                    if imp.symbol_name == sym or (parent and imp.symbol_name == parent):
                        as_name = imp.alias or imp.symbol_name
                        aliases[as_name] = (parent, sym)
                        evidence.append(
                            {
                                "level": EvidenceStrength.LEVEL_2_EXACT_CALL.value,
                                "tier": "HIGH",
                                "score": 0.95,
                                "line": imp.line,
                                "source_ref": f"{test_file}:{imp.line}",
                                "reason": f"Directly imports target symbol '{imp.symbol_name}' from {mod} at line {imp.line}.",
                            }
                        )

                if not any(imp.symbol_name == s for _, s in targets):
                    snake_name = re.sub(
                        r"(?<!^)(?=[A-Z])", "_", imp.symbol_name
                    ).lower()
                    is_primary = any(
                        sf.endswith(f"/{imp.symbol_name.lower()}.py")
                        or sf.endswith(f"/{imp.symbol_name.lower()}_service.py")
                        or sf.endswith(f"/{snake_name}.py")
                        or sf.endswith(f"/{snake_name}_service.py")
                        for sf in seed_files
                    )
                    evidence.append(
                        {
                            "level": EvidenceStrength.LEVEL_2_EXACT_CALL.value
                            if is_primary
                            else EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value,
                            "tier": "HIGH" if is_primary else "MEDIUM",
                            "score": 0.90 if is_primary else 0.75,
                            "line": imp.line,
                            "source_ref": f"{test_file}:{imp.line}",
                            "reason": f"Imports {'primary' if is_primary else 'related'} symbol '{imp.symbol_name}' from changed module/package {mod} at line {imp.line}.",
                        }
                    )

        # 2. Module imports
        for mod_name, alias, line in facts.imports_module:
            if mod_name in seed_mods or mod_name in seed_packages:
                evidence.append(
                    {
                        "level": EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value,
                        "tier": "MEDIUM",
                        "score": 0.70,
                        "line": line,
                        "source_ref": f"{test_file}:{line}",
                        "reason": f"Imports changed module '{mod_name}' at line {line}.",
                    }
                )

        # 3. Function/method calls
        for call in facts.calls:
            for parent, sym in targets:
                matched = False
                if parent:
                    if call.call_repr.endswith(f".{sym}"):
                        pfx = call.prefix
                        if pfx and (
                            pfx.lower() == parent.lower()
                            or pfx in aliases
                            or (
                                pfx in ("s", "self")
                                and (is_seed_mod or is_seed_pkg or parent in aliases)
                            )
                        ):
                            matched = True
                else:
                    if call.call_repr == sym or call.call_repr in aliases:
                        matched = True
                    elif call.call_repr.endswith(f".{sym}"):
                        pfx = call.prefix
                        if pfx and (
                            pfx in aliases or pfx in seed_mods or pfx in seed_packages
                        ):
                            matched = True

                if matched:
                    evidence.append(
                        {
                            "level": EvidenceStrength.LEVEL_1_EXACT_SYMBOL.value,
                            "tier": "HIGH",
                            "score": 1.00,
                            "line": call.line,
                            "source_ref": f"{test_file}:{call.line}",
                            "reason": f"Directly calls target symbol '{call.call_repr}' at line {call.line}.",
                        }
                    )

        # 4. API routes
        for rf in facts.routes:
            for r in api_routes:
                clean_r = r.split()[0] if " " in r else r
                if clean_r == rf.url or (
                    len(clean_r) > 2 and rf.url.startswith(clean_r)
                ):
                    evidence.append(
                        {
                            "level": EvidenceStrength.LEVEL_4_API_CONTRACT.value,
                            "tier": "HIGH",
                            "score": 0.85,
                            "line": rf.line,
                            "source_ref": f"{test_file}:{rf.line}",
                            "reason": f"Invokes affected API route '{rf.url}' at line {rf.line}.",
                        }
                    )

        return evidence
