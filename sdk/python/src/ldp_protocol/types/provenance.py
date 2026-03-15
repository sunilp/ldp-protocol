"""LDP provenance tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from ldp_protocol.types.payload import PayloadMode
from ldp_protocol.types.verification import (
    EvidenceRef,
    ProvenanceEntry,
    VerificationStatus,
)


class Provenance(BaseModel):
    """Provenance metadata attached to every LDP task result.

    Tracks who produced a result, which model, confidence, and verification status.
    """

    produced_by: str
    model_version: str
    payload_mode_used: PayloadMode = PayloadMode.SEMANTIC_FRAME
    confidence: float | None = None
    verified: bool = False  # Deprecated: use verification_status
    session_id: str | None = None
    timestamp: str | None = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tokens_used: int | None = None
    cost_usd: float | None = None
    contract_id: str | None = None
    contract_satisfied: bool | None = None
    contract_violations: list[str] = Field(default_factory=list)

    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    lineage: list[ProvenanceEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> Provenance:
        """Sync verified bool with verification_status."""
        if self.verification_status == VerificationStatus.UNVERIFIED and self.verified:
            self.verification_status = VerificationStatus.SELF_VERIFIED
        self.verified = self.verification_status != VerificationStatus.UNVERIFIED
        return self

    @classmethod
    def create(cls, delegate_id: str, model_version: str, **kwargs) -> Provenance:
        """Create a new provenance record with auto-timestamp."""
        return cls(
            produced_by=delegate_id,
            model_version=model_version,
            **kwargs,
        )
