"""Index Unit Builder."""

from typing import Optional

from ria.domain.index.units import ASTUnit, FileUnit, ParseUnit, ParserResult


class IndexUnitBuilder:
    """Builder constructing immutable ASTUnit and ParseUnit domain objects from FileUnit and ParserResult."""

    def build_parse_unit(
        self,
        file_unit: FileUnit,
        parser_result: Optional[ParserResult],
        parse_duration_ms: float,
    ) -> ParseUnit:
        """Combine FileUnit, ParserResult, and timing into an immutable ParseUnit."""
        ast_unit: Optional[ASTUnit] = None

        if parser_result and parser_result.is_success and parser_result.ast_root_node:
            ast_unit = ASTUnit(
                path=file_unit.path,
                language=file_unit.language,
                root_node=parser_result.ast_root_node,
                total_nodes=parser_result.total_nodes,
            )

        return ParseUnit(
            file_unit=file_unit,
            ast_unit=ast_unit,
            parse_duration_ms=parse_duration_ms,
            is_truncated=False,
        )
