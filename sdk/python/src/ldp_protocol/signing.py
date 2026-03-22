"""HMAC message signing and verification for LDP envelopes."""
from __future__ import annotations

import hashlib
import hmac as hmac_mod

from ldp_protocol.types.messages import LdpEnvelope


def sign_envelope(envelope: LdpEnvelope, secret: str) -> str:
    """Sign an envelope using canonical field order (cross-SDK compatible)."""
    mac = hmac_mod.new(secret.encode(), digestmod=hashlib.sha256)

    # Canonical signing input: same order as Rust
    mac.update(envelope.from_.encode())
    mac.update(b"|")
    mac.update(envelope.to.encode())
    mac.update(b"|")
    mac.update(envelope.session_id.encode())
    mac.update(b"|")
    mac.update(envelope.timestamp.encode())
    mac.update(b"|")
    mac.update(envelope.message_id.encode())
    # Include nonce in signing payload only when present (backward compat)
    if envelope.nonce is not None:
        mac.update(b"|")
        mac.update(envelope.nonce.encode())
    mac.update(b"|")

    body = envelope.body
    body_type = body.type

    if body_type == "HELLO" and body.delegate_id:
        mac.update(body.delegate_id.encode())
    elif body_type == "SESSION_ACCEPT" and body.session_id:
        mac.update(body.session_id.encode())
    elif body_type == "SESSION_REJECT" and body.reason:
        mac.update(body.reason.encode())
    elif body_type == "TASK_SUBMIT":
        if body.task_id:
            mac.update(body.task_id.encode())
        mac.update(b"|")
        if body.skill:
            mac.update(body.skill.encode())
    elif body_type in ("TASK_UPDATE", "TASK_RESULT", "TASK_FAILED", "TASK_CANCEL"):
        if body.task_id:
            mac.update(body.task_id.encode())

    mac.update(b"|")
    mac.update(body_type.encode())

    return mac.hexdigest()


def verify_envelope(envelope: LdpEnvelope, secret: str, signature: str) -> bool:
    """Verify using constant-time comparison."""
    expected = sign_envelope(envelope, secret)
    return hmac_mod.compare_digest(expected, signature)


def apply_signature(envelope: LdpEnvelope, secret: str) -> None:
    """Apply signature to envelope (mutates in place)."""
    envelope.signature = sign_envelope(envelope, secret)
    envelope.signature_algorithm = "hmac-sha256"
