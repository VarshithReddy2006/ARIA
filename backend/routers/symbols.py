"""Symbols router — AST Symbol Intelligence (PH2-002).

Endpoints:
  GET /api/symbols/{owner}/{repo}/file/{file_path}
  GET /api/symbols/{owner}/{repo}/definition/{symbol_name}
  GET /api/symbols/{owner}/{repo}/references/{symbol_name}
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_symbol_service
from services.symbol_service import SymbolService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/symbols", tags=["Symbols"])


@router.get("/{owner}/{repo}/file/{file_path:path}")
async def get_symbols_for_file(
    owner: str,
    repo: str,
    file_path: str,
    service: SymbolService = Depends(get_symbol_service),
):
    """Return all symbols (functions, classes, methods, etc.) defined in a file.

    The symbol index is built automatically during POST /api/architecture/build.
    Re-run that endpoint to refresh the index after code changes.
    """
    repo_name = f"{owner}/{repo}"
    try:
        symbols = await asyncio.to_thread(
            service.get_file_symbols, repo_name, file_path
        )
        if symbols is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No symbol index found for '{repo_name}'. "
                    "Run POST /api/architecture/build first."
                ),
            )
        return {
            "file": file_path,
            "repo": repo_name,
            "symbol_count": len(symbols),
            "symbols": [s.model_dump() for s in symbols],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "get_symbols_for_file failed for %s/%s: %s",
            repo_name,
            file_path,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/definition/{symbol_name}")
async def get_symbol_definition(
    owner: str,
    repo: str,
    symbol_name: str,
    service: SymbolService = Depends(get_symbol_service),
):
    """Look up the definition of a named symbol (function, class, method, etc.).

    Returns the first match when multiple symbols share a name, preferring
    classes over functions, functions over methods.
    """
    repo_name = f"{owner}/{repo}"
    try:
        definition = await asyncio.to_thread(
            service.get_definition, repo_name, symbol_name
        )
        if definition is None:
            if not service.index_exists(repo_name):
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"No symbol index found for '{repo_name}'. "
                        "Run POST /api/architecture/build first."
                    ),
                )
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{symbol_name}' not found in repo '{repo_name}'.",
            )
        return {
            "symbol": symbol_name,
            "repo": repo_name,
            "definition": definition.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "get_symbol_definition failed for %s/%s: %s",
            repo_name,
            symbol_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{owner}/{repo}/references/{symbol_name}")
async def get_symbol_references(
    owner: str,
    repo: str,
    symbol_name: str,
    service: SymbolService = Depends(get_symbol_service),
):
    """Return all symbols in the repository that share the given name.

    MVP implementation uses name-based matching across the entire symbol index.
    Full cross-file call-graph analysis is planned for PH2-003.
    """
    repo_name = f"{owner}/{repo}"
    try:
        references = await asyncio.to_thread(
            service.get_references, repo_name, symbol_name
        )
        if references is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No symbol index found for '{repo_name}'. "
                    "Run POST /api/architecture/build first."
                ),
            )
        return {
            "symbol": symbol_name,
            "repo": repo_name,
            "references": [r.model_dump() for r in references],
            "reference_count": len(references),
            "note": (
                "MVP: name-based matching only. "
                "Full cross-file call graph planned for PH2-003."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "get_symbol_references failed for %s/%s: %s",
            repo_name,
            symbol_name,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))
