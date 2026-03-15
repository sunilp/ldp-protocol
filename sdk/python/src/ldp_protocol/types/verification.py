"""LDP verification and lineage types."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    SELF_VERIFIED = "self_verified"
    PEER_VERIFIED = "peer_verified"
    TOOL_VERIFIED = "tool_verified"
    HUMAN_VERIFIED = "human_verified"


class EvidenceRef(BaseModel):
    source: str
    kind: str
    uri: str | None = None
    summary: str | None = None


class ProvenanceEntry(BaseModel):
    delegate_id: str
    model_version: str
    step: str
    timestamp: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
