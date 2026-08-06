"""SQLite Implementation of FactStorePort."""

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Optional, Union

from ria.domain.index.value_objects import FilePath, Location
from ria.domain.resolution import (
    QualifiedName,
    RelationKind,
    ResolvedFactSet,
    SemanticRelation,
    SemanticSymbol,
    SymbolKind,
    SymbolModifiers,
    SymbolMoniker,
    Visibility,
)
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.infrastructure.exceptions import DatabaseError
from ria.ports.storage.fact_store import FactStorePort


class SQLiteFactStoreAdapter(FactStorePort):
    """SQLite relational FactStore adapter storing symbols and relations partitioned by (repo_id, commit_sha)."""

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        self._db_path = str(db_path)
        self._persistent_conn: Optional[sqlite3.Connection] = None

        if self._db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row

        self._initialize_schema()

    def _get_connection(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS facts (
            repo_id TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            moniker TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            visibility TEXT NOT NULL,
            file_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            start_col INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            end_col INTEGER NOT NULL,
            modifiers_json TEXT,
            PRIMARY KEY (repo_id, commit_sha, moniker)
        );

        CREATE TABLE IF NOT EXISTS derived_relations (
            repo_id TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            source_moniker TEXT NOT NULL,
            target_moniker TEXT NOT NULL,
            relation_kind TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            start_col INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            end_col INTEGER NOT NULL,
            PRIMARY KEY (repo_id, commit_sha, source_moniker, target_moniker, relation_kind)
        );

        CREATE INDEX IF NOT EXISTS idx_facts_file ON facts(repo_id, commit_sha, file_path);
        CREATE INDEX IF NOT EXISTS idx_relations_source ON derived_relations(repo_id, commit_sha, source_moniker);
        """
        conn = self._get_connection()
        try:
            with conn:
                conn.executescript(schema)
        except sqlite3.Error as err:
            raise DatabaseError(f"Failed to initialize SQLite FactStore schema: {err}") from err
        finally:
            if self._persistent_conn is None:
                conn.close()

    def save_fact_set(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        fact_set: ResolvedFactSet,
    ) -> None:
        conn = self._get_connection()
        repo_val = repo_id.repo_id.value
        sha_val = commit.sha

        try:
            with conn:
                # 1. Clear existing facts for this commit partition
                conn.execute("DELETE FROM facts WHERE repo_id = ? AND commit_sha = ?", (repo_val, sha_val))
                conn.execute("DELETE FROM derived_relations WHERE repo_id = ? AND commit_sha = ?", (repo_val, sha_val))

                # 2. Insert symbols
                for sym in fact_set.symbols:
                    mods_json = json.dumps({
                        "is_static": sym.modifiers.is_static,
                        "is_async": sym.modifiers.is_async,
                        "is_abstract": sym.modifiers.is_abstract,
                        "is_readonly": sym.modifiers.is_readonly,
                        "is_exported": sym.modifiers.is_exported,
                    })
                    conn.execute(
                        """
                        INSERT INTO facts (
                            repo_id, commit_sha, moniker, name, qualified_name, kind, visibility, file_path,
                            start_line, start_col, end_line, end_col, modifiers_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            repo_val,
                            sha_val,
                            sym.moniker.value,
                            sym.name,
                            sym.qualified_name.dotted_path,
                            sym.kind.value,
                            sym.visibility.value,
                            sym.path.relative_path,
                            sym.location.start_line,
                            sym.location.start_col,
                            sym.location.end_line,
                            sym.location.end_col,
                            mods_json,
                        ),
                    )

                # 3. Insert calls/relations as derived relations
                for rel in fact_set.relations:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO derived_relations (
                            repo_id, commit_sha, source_moniker, target_moniker, relation_kind,
                            start_line, start_col, end_line, end_col
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            repo_val,
                            sha_val,
                            rel.source.value,
                            rel.target.value,
                            rel.kind.value,
                            rel.location.start_line,
                            rel.location.start_col,
                            rel.location.end_line,
                            rel.location.end_col,
                        ),
                    )

                for call in fact_set.calls:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO derived_relations (
                            repo_id, commit_sha, source_moniker, target_moniker, relation_kind,
                            start_line, start_col, end_line, end_col
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            repo_val,
                            sha_val,
                            call.caller_moniker.value,
                            call.callee_moniker.value,
                            RelationKind.CALLS.value,
                            call.location.start_line,
                            call.location.start_col,
                            call.location.end_line,
                            call.location.end_col,
                        ),
                    )

        except sqlite3.Error as err:
            raise DatabaseError(f"Failed to save ResolvedFactSet to FactStore: {err}") from err
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_symbols(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        path: Optional[FilePath] = None,
    ) -> Sequence[SemanticSymbol]:
        conn = self._get_connection()
        repo_val = repo_id.repo_id.value
        sha_val = commit.sha

        try:
            if path is not None:
                cursor = conn.execute(
                    "SELECT * FROM facts WHERE repo_id = ? AND commit_sha = ? AND file_path = ?",
                    (repo_val, sha_val, path.relative_path),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM facts WHERE repo_id = ? AND commit_sha = ?",
                    (repo_val, sha_val),
                )

            symbols: list[SemanticSymbol] = []
            for row in cursor.fetchall():
                mods_data = json.loads(row["modifiers_json"]) if row["modifiers_json"] else {}
                mods = SymbolModifiers(
                    is_static=mods_data.get("is_static", False),
                    is_async=mods_data.get("is_async", False),
                    is_abstract=mods_data.get("is_abstract", False),
                    is_readonly=mods_data.get("is_readonly", False),
                    is_exported=mods_data.get("is_exported", False),
                )

                sym = SemanticSymbol(
                    moniker=SymbolMoniker(value=row["moniker"]),
                    name=row["name"],
                    qualified_name=QualifiedName(dotted_path=row["qualified_name"]),
                    kind=SymbolKind(row["kind"]),
                    visibility=Visibility(row["visibility"]),
                    path=FilePath(relative_path=row["file_path"]),
                    location=Location(
                        start_line=row["start_line"],
                        start_col=row["start_col"],
                        end_line=row["end_line"],
                        end_col=row["end_col"],
                    ),
                    modifiers=mods,
                )
                symbols.append(sym)

            return tuple(symbols)
        except sqlite3.Error as err:
            raise DatabaseError(f"Failed to query symbols from FactStore: {err}") from err
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_relations(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        source_moniker: Optional[SymbolMoniker] = None,
    ) -> Sequence[SemanticRelation]:
        conn = self._get_connection()
        repo_val = repo_id.repo_id.value
        sha_val = commit.sha

        try:
            if source_moniker is not None:
                cursor = conn.execute(
                    "SELECT * FROM derived_relations WHERE repo_id = ? AND commit_sha = ? AND source_moniker = ?",
                    (repo_val, sha_val, source_moniker.value),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM derived_relations WHERE repo_id = ? AND commit_sha = ?",
                    (repo_val, sha_val),
                )

            relations: list[SemanticRelation] = []
            for row in cursor.fetchall():
                rel = SemanticRelation(
                    source=SymbolMoniker(value=row["source_moniker"]),
                    target=SymbolMoniker(value=row["target_moniker"]),
                    kind=RelationKind(row["relation_kind"]),
                    location=Location(
                        start_line=row["start_line"],
                        start_col=row["start_col"],
                        end_line=row["end_line"],
                        end_col=row["end_col"],
                    ),
                )
                relations.append(rel)

            return tuple(relations)
        except sqlite3.Error as err:
            raise DatabaseError(f"Failed to query relations from FactStore: {err}") from err
        finally:
            if self._persistent_conn is None:
                conn.close()

    def delete_facts(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> bool:
        conn = self._get_connection()
        repo_val = repo_id.repo_id.value
        sha_val = commit.sha

        try:
            with conn:
                c1 = conn.execute("DELETE FROM facts WHERE repo_id = ? AND commit_sha = ?", (repo_val, sha_val))
                c2 = conn.execute("DELETE FROM derived_relations WHERE repo_id = ? AND commit_sha = ?", (repo_val, sha_val))
                return (c1.rowcount + c2.rowcount) > 0
        except sqlite3.Error as err:
            raise DatabaseError(f"Failed to delete facts from FactStore: {err}") from err
        finally:
            if self._persistent_conn is None:
                conn.close()
