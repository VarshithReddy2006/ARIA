"""Tests for qualified symbol disambiguation and contextual file resolution."""

from datetime import datetime, timezone
from models.symbol import Symbol, SymbolIndex
from services.symbol_service import SymbolService


def test_qualified_symbol_resolution():
    sym1 = Symbol(
        name="send",
        type="method",
        file_path="src/requests/sessions.py",
        line_number=500,
        language="python",
        parent_class="Session",
    )
    sym2 = Symbol(
        name="send",
        type="method",
        file_path="src/requests/adapters.py",
        line_number=350,
        language="python",
        parent_class="HTTPAdapter",
    )

    index = SymbolIndex(
        repo="psf/requests",
        generated_at=datetime.now(timezone.utc).isoformat(),
        symbol_count=2,
        symbols=[sym1, sym2],
        file_symbol_map={
            "src/requests/sessions.py": [sym1],
            "src/requests/adapters.py": [sym2],
        },
        name_symbol_map={"send": [sym1, sym2]},
    )

    svc = SymbolService()
    svc.load = lambda repo: index

    # 1. Qualified lookup "Session.send"
    res1 = svc.find_matching_symbols("psf/requests", "Session.send")
    assert len(res1) == 1
    assert res1[0].file_path == "src/requests/sessions.py"
    assert res1[0].parent_class == "Session"

    # 2. Qualified lookup "HTTPAdapter.send"
    res2 = svc.find_matching_symbols("psf/requests", "HTTPAdapter.send")
    assert len(res2) == 1
    assert res2[0].file_path == "src/requests/adapters.py"
    assert res2[0].parent_class == "HTTPAdapter"

    # 3. Contextual lookup with file_context
    res3 = svc.find_matching_symbols(
        "psf/requests", "send", file_context="src/requests/sessions.py"
    )
    assert len(res3) == 1
    assert res3[0].file_path == "src/requests/sessions.py"

    # 4. Ambiguous unqualified lookup returns both definitions
    res4 = svc.find_matching_symbols("psf/requests", "send")
    assert len(res4) == 2
