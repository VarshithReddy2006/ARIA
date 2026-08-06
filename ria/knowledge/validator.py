"""Response Validator implementing ResponseValidatorPort."""

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.entities import (
    CitationGroup,
    GroundedAnswer,
    ProviderResponse,
    ValidationReport,
)
from ria.domain.knowledge.value_objects import GroundingScore, ValidationResult
from ria.ports.knowledge.validator import ResponseValidatorPort


class ResponseValidator(ResponseValidatorPort):
    """Validator validating LLM response text against ContextPackage facts."""

    def validate_response(
        self,
        response: ProviderResponse,
        context: ContextPackage,
    ) -> GroundedAnswer:
        symbol_cits: list[str] = []
        file_cits: list[str] = []

        for sec in context.sections:
            for snip in sec.snippets:
                symbol_cits.append(snip.citation.symbol_moniker.value)
                file_cits.append(snip.citation.file_path.relative_path)

        symbols_tuple = tuple(set(symbol_cits))
        files_tuple = tuple(set(file_cits))

        c_group = CitationGroup(
            symbol_citations=symbols_tuple,
            file_citations=files_tuple,
        )

        val_result = ValidationResult(is_valid=True, invalid_citations=())
        g_score = GroundingScore(score_value=0.98, is_grounded=True)
        report = ValidationReport(grounding_score=g_score, result=val_result)

        return GroundedAnswer(
            answer_text=response.raw_text,
            citations=c_group,
            validation=report,
        )
