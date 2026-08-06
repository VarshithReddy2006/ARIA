"""Common Value Objects for the RIA Domain."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from ria.domain.common.base import ValueObject


@dataclass(frozen=True, slots=True)
class Timestamp(ValueObject):
    """Immutable representation of a UTC timestamp."""

    iso_format: str

    def _validate_invariants(self) -> None:
        if not self.iso_format:
            raise ValueError("Timestamp ISO string cannot be empty.")

    @classmethod
    def now(cls) -> "Timestamp":
        """Factory method returning current UTC timestamp in ISO 8601 format."""
        return cls(iso_format=datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_datetime(cls, dt: datetime) -> "Timestamp":
        """Factory method from datetime object, converting to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return cls(iso_format=dt.isoformat())


@dataclass(frozen=True, slots=True)
class UUIDv4(ValueObject):
    """Immutable representation of a UUID version 4 identity."""

    value: str

    def _validate_invariants(self) -> None:
        try:
            val = UUID(self.value, version=4)
            if str(val) != self.value.lower():
                raise ValueError(f"UUID string '{self.value}' is not normalized lower-case.")
        except Exception as err:
            raise ValueError(f"Invalid UUIDv4 value '{self.value}': {err}") from err

    @classmethod
    def generate(cls) -> "UUIDv4":
        import uuid
        return cls(value=str(uuid.uuid4()))
