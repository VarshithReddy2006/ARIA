"""Python SDK Response Models."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True, slots=True)
class SDKResponse:
    """Standardized response container for Python SDK."""

    is_success: bool
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
