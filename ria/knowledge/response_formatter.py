"""Response Formatter."""

import json

from ria.domain.knowledge.entities import GroundedAnswer


class ResponseFormatter:
    """Formatter rendering GroundedAnswer into Markdown, Text, or JSON formats."""

    def format_markdown(self, answer: GroundedAnswer) -> str:
        lines: list[str] = [
            "# Grounded Answer",
            answer.answer_text,
            "",
            "### Citations",
        ]
        for sym in answer.citations.symbol_citations:
            lines.append(f"- `Symbol`: `{sym}`")
        for fpath in answer.citations.file_citations:
            lines.append(f"- `File`: `{fpath}`")

        return "\n".join(lines)

    def format_text(self, answer: GroundedAnswer) -> str:
        return f"{answer.answer_text}\n\nCitations:\n- Symbols: {', '.join(answer.citations.symbol_citations)}\n- Files: {', '.join(answer.citations.file_citations)}"

    def format_json(self, answer: GroundedAnswer) -> str:
        data = {
            "answer": answer.answer_text,
            "citations": {
                "symbols": list(answer.citations.symbol_citations),
                "files": list(answer.citations.file_citations),
            },
            "grounding_score": answer.validation.grounding_score.score_value,
            "is_grounded": answer.validation.grounding_score.is_grounded,
        }
        return json.dumps(data, indent=2)
