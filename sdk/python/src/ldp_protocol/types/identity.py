"""LDP delegate identity card."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ldp_protocol.types.capability import LdpCapability
from ldp_protocol.types.payload import PayloadMode
from ldp_protocol.types.trust import TrustDomain


class LdpIdentityCard(BaseModel):
    """Full LDP identity card for a delegate.

    This is the rich identity representation that enables intelligent routing:
    model family, quality scores, reasoning profiles, cost/latency hints.
    """

    delegate_id: str
    name: str
    description: str | None = None
    model_family: str
    model_version: str
    weights_fingerprint: str | None = None
    trust_domain: TrustDomain
    context_window: int
    reasoning_profile: str | None = None
    cost_profile: str | None = None
    latency_profile: str | None = None
    jurisdiction: str | None = None
    capabilities: list[LdpCapability] = Field(default_factory=list)
    supported_payload_modes: list[PayloadMode] = Field(
        default_factory=lambda: [PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT]
    )
    endpoint: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)

    def capability(self, name: str) -> LdpCapability | None:
        """Find a capability by name."""
        for cap in self.capabilities:
            if cap.name == name:
                return cap
        return None

    def quality_score(self, skill: str) -> float:
        """Get the quality score for a skill, or 0.0 if not found."""
        cap = self.capability(skill)
        if cap and cap.quality and cap.quality.quality_score is not None:
            return cap.quality.quality_score
        return 0.0

    def cost(self, skill: str) -> float:
        """Get the cost per call for a skill, or inf if not found."""
        cap = self.capability(skill)
        if cap and cap.quality and cap.quality.cost_per_call_usd is not None:
            return cap.quality.cost_per_call_usd
        return float("inf")

    def latency(self, skill: str) -> int:
        """Get the p50 latency for a skill, or max int if not found."""
        cap = self.capability(skill)
        if cap and cap.quality and cap.quality.latency_p50_ms is not None:
            return cap.quality.latency_p50_ms
        return 2**31
