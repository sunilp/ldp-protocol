"""LDP trust domain types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TrustDomain(BaseModel):
    """A trust domain — a named security boundary for delegates."""

    name: str
    allow_cross_domain: bool = False
    trusted_peers: list[str] = Field(default_factory=list)

    def trusts(self, peer: str) -> bool:
        """Check if this domain trusts a peer domain."""
        if self.name == peer:
            return True
        return self.allow_cross_domain and peer in self.trusted_peers
