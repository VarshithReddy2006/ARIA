"""Person value object.

Twin Spec section 3.2 defines ``Person`` as an entity of the Social facet with
identity resolution across multiple email addresses and forge accounts. That
resolution is out of scope for Milestone 1.

What Milestone 1 requires is the *raw* authorship signature attached to a
commit, which git provides as a name and email pair. This module models exactly
that and no more: :class:`PersonRef` is an unresolved reference, deliberately
distinct from the future ``Person`` aggregate.

Keeping the two apart matters. Merging git signatures into a canonical person is
a fallible heuristic; the Social facet will attach a confidence to it. Recording
the raw signature separately means the resolved identity can be recomputed
without the original observation ever being lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["PersonRef"]


@dataclass(frozen=True)
class PersonRef:
    """An unresolved authorship signature as recorded by version control.

    Attributes:
        name: Display name from the commit signature. May be empty when a commit
            was created without a configured name.
        email: Email address from the commit signature, lowercased. May be
            ``None`` when absent from the signature.
    """

    name: str
    email: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", (self.name or "").strip())
        if self.email is not None:
            normalised = self.email.strip().lower()
            object.__setattr__(self, "email", normalised or None)

    @property
    def identity_key(self) -> str:
        """Best available stable key for this signature.

        Email is preferred because it is far more stable than a display name.
        Falls back to the lowercased name, and finally to a fixed sentinel so
        that the key is never empty.

        Returns:
            A non-empty key suitable for grouping signatures prior to proper
            identity resolution in the Social facet.
        """
        if self.email:
            return self.email
        if self.name:
            return self.name.lower()
        return "unknown"

    def __str__(self) -> str:
        if self.name and self.email:
            return f"{self.name} <{self.email}>"
        return self.name or self.email or "unknown"
