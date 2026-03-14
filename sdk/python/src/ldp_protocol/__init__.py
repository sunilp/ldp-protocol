"""LDP — LLM Delegate Protocol.

Identity-aware communication protocol for multi-agent LLM systems.
LDP adds delegation intelligence on top of A2A and MCP: rich identity,
progressive payload modes, governed sessions, structured provenance,
and trust domains.
"""

from ldp_protocol.types import (
    LdpCapability,
    LdpEnvelope,
    LdpIdentityCard,
    LdpMessageBody,
    LdpSession,
    NegotiatedPayload,
    PayloadMode,
    Provenance,
    QualityMetrics,
    SessionConfig,
    SessionState,
    TrustDomain,
)
from ldp_protocol.client import LdpClient
from ldp_protocol.delegate import LdpDelegate
from ldp_protocol.router import LdpRouter

__version__ = "0.1.0"

__all__ = [
    # Types
    "LdpIdentityCard",
    "LdpCapability",
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
]
