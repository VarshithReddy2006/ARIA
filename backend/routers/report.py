"""Router exposing report endpoints versioned under /api/v1/report."""

import sys

from fastapi import APIRouter, HTTPException, Query, Response

from backend.dependencies import (
    get_report_composer,
    get_html_renderer,
    get_markdown_renderer,
    get_pdf_renderer,
)
from models.report import ReportDataModel
from storage.migrations import get_db_connection


class _ReloadSafeDependency:
    """Resolve a compatibility dependency from the currently loaded router module."""

    def __init__(self, name: str, getter_fn) -> None:
        self._name = name
        self._getter = getter_fn

    def __getattr__(self, attribute: str) -> object:
        module = sys.modules.get(__name__)
        dependency = getattr(module, self._name, None)
        if dependency is None or dependency is self:
            dependency = self._getter()
        return getattr(dependency, attribute)


report_composer = _ReloadSafeDependency("report_composer", get_report_composer)
html_renderer = _ReloadSafeDependency("html_renderer", get_html_renderer)
markdown_renderer = _ReloadSafeDependency("markdown_renderer", get_markdown_renderer)
pdf_renderer = _ReloadSafeDependency("pdf_renderer", get_pdf_renderer)

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/{owner}/{repo}/build", response_model=ReportDataModel)
def build_report(owner: str, repo: str) -> ReportDataModel:
    """Triggers report generation for the specified repository and returns the model."""
    repo_name = f"{owner}/{repo}"
    try:
        report = report_composer.compose_report(repo_name)
        return report
    except ValueError as exc:
        raise HTTPException(status_code=412, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to build report: {str(exc)}"
        )


@router.get("/{owner}/{repo}/summary")
def get_report_summary(owner: str, repo: str):
    """Fetches the latest summarized health scores and grade for a repository."""
    repo_name = f"{owner}/{repo}"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT overall_score, grade, generated_at 
            FROM repo_reports 
            WHERE repo_name = ? 
            ORDER BY generated_at DESC 
            LIMIT 1
            """,
            (repo_name,),
        )
        row = cursor.fetchone()
        if row is None:
            # If not in DB, compose it dynamically
            try:
                report = report_composer.compose_report(repo_name)
                return {
                    "repo_name": repo_name,
                    "score": report.scores.overall,
                    "grade": report.scores.grade,
                    "analyzed_at": report.metadata.generated_at,
                }
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))

        return {
            "repo_name": repo_name,
            "score": row[0],
            "grade": row[1],
            "analyzed_at": row[2],
        }
    finally:
        conn.close()


@router.get("/{owner}/{repo}/download")
def download_report(
    owner: str, repo: str, format: str = Query("html", pattern="^(html|pdf|markdown)$")
):
    """Downloads the compiled health report in HTML, PDF (print-friendly HTML), or Markdown format."""
    repo_name = f"{owner}/{repo}"
    try:
        report = report_composer.compose_report(repo_name)

        if format == "markdown":
            content_bytes = markdown_renderer.render(report)
            filename = f"{owner}_{repo}_report.md"
            media_type = "text/markdown"
        elif format == "pdf":
            content_bytes = pdf_renderer.render(report)
            filename = f"{owner}_{repo}_report.html"
            media_type = "text/html"
        else:
            content_bytes = html_renderer.render(report)
            filename = f"{owner}_{repo}_report.html"
            media_type = "text/html"

        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=content_bytes, media_type=media_type, headers=headers)
    except ValueError as exc:
        raise HTTPException(status_code=412, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate download: {str(exc)}"
        )
