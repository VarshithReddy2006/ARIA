"""SQLite persistence implementation for Milestone 10 Multi-Agent Developer Platform."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

from ria.domain.errors import StorageError
from ria.domain.models.agent_result import AgentStatistics, ExecutionReport
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider

__all__ = ["SqliteAgentPlatformStore"]


class SqliteAgentPlatformStore:
    """SQLite storage for ExecutionReports and Agent Sessions."""

    def __init__(self, connections: ConnectionProvider) -> None:
        self._connections = connections

    def get_report(self, session_id: str) -> Optional[ExecutionReport]:
        conn = self._connections.connection()
        try:
            cursor = conn.execute(
                "SELECT report_json FROM ria_agent_report WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            return ExecutionReport(
                session_id=data["session_id"],
                summary_text=data["summary_text"],
                statistics=AgentStatistics(
                    tasks_scheduled=data["statistics"]["scheduled"],
                    tasks_succeeded=data["statistics"]["succeeded"],
                    tasks_failed=data["statistics"]["failed"],
                ),
            )
        except Exception as exc:
            raise StorageError(f"failed to read agent report: {exc}") from exc

    def put_report(self, report: ExecutionReport) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        report_json = json.dumps(
            {
                "session_id": report.session_id,
                "summary_text": report.summary_text,
                "statistics": {
                    "scheduled": report.statistics.tasks_scheduled,
                    "succeeded": report.statistics.tasks_succeeded,
                    "failed": report.statistics.tasks_failed,
                },
            }
        )

        conn = self._connections.connection()
        try:
            conn.execute(
                """
                INSERT INTO ria_agent_report (session_id, report_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET report_json = excluded.report_json, created_at = excluded.created_at
                """,
                (report.session_id, report_json, created_at),
            )
        except Exception as exc:
            raise StorageError(f"failed to write agent report: {exc}") from exc
