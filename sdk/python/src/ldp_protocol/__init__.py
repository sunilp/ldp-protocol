"""LDP — LLM Delegate Protocol.

Identity-aware communication protocol for multi-agent LLM systems.
LDP adds delegation intelligence on top of A2A and MCP: rich identity,
progressive payload modes, governed sessions, structured provenance,
and trust domains.
"""

from ldp_protocol.types import (
    BudgetPolicy,
    ClaimType,
    DelegationContract,
    ErrorSeverity,
    FailureCategory,
    FailurePolicy,
    LdpCapability,
    LdpEnvelope,
    LdpError,
    LdpIdentityCard,
    LdpMessageBody,
    LdpSession,
    NegotiatedPayload,
    PayloadMode,
    PolicyEnvelope,
    Provenance,
    QualityMetrics,
    SessionConfig,
    SessionState,
    TrustDomain,
)
from ldp_protocol.client import LdpClient
from ldp_protocol.delegate import LdpDelegate
from ldp_protocol.router import LdpRouter, RoutingStrategy
from ldp_protocol.signing import sign_envelope, verify_envelope, apply_signature

__version__ = "0.2.0"

__all__ = [
    # Types
    "BudgetPolicy",
    "ClaimType",
    "DelegationContract",
    "ErrorSeverity",
    "FailureCategory",
    "FailurePolicy",
    "LdpError",
    "LdpIdentityCard",
    "LdpCapability",
    "PolicyEnvelope",
    "QualityMetrics",
    "TrustDomain",
    "PayloadMode",
    "NegotiatedPayload",
    "SessionConfig",
    "SessionState",
    "LdpSession",
    "LdpEnvelope",
    "LdpMessageBody",
    "Provenance",
    # Client
    "LdpClient",
    # Delegate
    "LdpDelegate",
    # Router
    "LdpRouter",
    "RoutingStrategy",
    # Signing
    "sign_envelope",
    "verify_envelope",
    "apply_signature",
]
