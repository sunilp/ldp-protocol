"""LDP trust domain types."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TrustDomain(BaseModel):
    """A trust domain — a named security boundary for delegates."""

    name: str
    allow_cross_domain: bool = False
    trusted_peers: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Trust domain name must not be empty")
        return v

    def trusts(self, peer: str) -> bool:
        """Check if this domain trusts a peer domain."""
        if self.name == peer:
            return True
        return self.allow_cross_domain and peer in self.trusted_peers

    def mutually_trusts(self, peer: TrustDomain) -> bool:
        """Check if two domains mutually trust each other."""
        return self.trusts(peer.name) and peer.trusts(self.name)
