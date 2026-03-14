"""LDP session types."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from ldp_protocol.types.payload import NegotiatedPayload, PayloadMode
from ldp_protocol.types.trust import TrustDomain


class SessionState(str, Enum):
    """State of an LDP session."""

    INITIATING = "initiating"
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    FAILED = "failed"


class SessionConfig(BaseModel):
    """Configuration for establishing a new LDP session."""

    preferred_payload_modes: list[PayloadMode] = Field(
        default_factory=lambda: [PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT]
    )
    ttl_secs: int = 3600
    required_trust_domain: str | None = None


class LdpSession(BaseModel):
    """An active LDP session."""

    session_id: str
    remote_url: str
    remote_delegate_id: str
    state: SessionState = SessionState.ACTIVE
    payload: NegotiatedPayload = Field(default_factory=NegotiatedPayload)
    trust_domain: TrustDomain
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_secs: int = 3600
    task_count: int = 0

    @property
    def is_active(self) -> bool:
        """Check if the session is still active and not expired."""
        if self.state != SessionState.ACTIVE:
            return False
        elapsed = (datetime.now(timezone.utc) - self.last_used).total_seconds()
        return elapsed < self.ttl_secs

    def touch(self) -> None:
        """Update last_used timestamp."""
        self.last_used = datetime.now(timezone.utc)
