"""LDP provenance tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ldp_protocol.types.payload import PayloadMode


class Provenance(BaseModel):
    """Provenance metadata attached to every LDP task result.

    Tracks who produced a result, which model, confidence, and verification status.
    """

    produced_by: str
    model_version: str
    payload_mode_used: PayloadMode = PayloadMode.SEMANTIC_FRAME
    confidence: float | None = None
    verified: bool = False
    session_id: str | None = None
    timestamp: str | None = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(cls, delegate_id: str, model_version: str, **kwargs) -> Provenance:
        """Create a new provenance record with auto-timestamp."""
        return cls(
            produced_by=delegate_id,
            model_version=model_version,
            **kwargs,
        )
