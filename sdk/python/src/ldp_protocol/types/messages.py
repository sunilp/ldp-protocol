"""LDP message types."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from ldp_protocol.types.error import LdpError
from ldp_protocol.types.payload import PayloadMode
from ldp_protocol.types.provenance import Provenance


class LdpMessageBody(BaseModel):
    """LDP message body — tagged union matching the Rust implementation."""

    type: str

    # HELLO
    delegate_id: str | None = None
    supported_modes: list[PayloadMode] | None = None

    # CAPABILITY_MANIFEST
    capabilities: Any | None = None

    # SESSION_PROPOSE
    config: dict[str, Any] | None = None

    # SESSION_ACCEPT
    session_id: str | None = None
    negotiated_mode: PayloadMode | None = None

    # SESSION_REJECT / SESSION_CLOSE
    reason: str | None = None

    # TASK_SUBMIT
    task_id: str | None = None
    skill: str | None = None
    input: Any | None = None

    # TASK_UPDATE
    progress: float | None = None
    message: str | None = None

    # TASK_RESULT
    output: Any | None = None
    provenance: Provenance | None = None

    # TASK_FAILED
    error: str | LdpError | None = None

    # ATTESTATION
    claim: Any | None = None
    evidence: Any | None = None

    @classmethod
    def hello(cls, delegate_id: str, supported_modes: list[PayloadMode]) -> LdpMessageBody:
        return cls(type="HELLO", delegate_id=delegate_id, supported_modes=supported_modes)

    @classmethod
    def capability_manifest(cls, capabilities: Any) -> LdpMessageBody:
        return cls(type="CAPABILITY_MANIFEST", capabilities=capabilities)

    @classmethod
    def session_propose(cls, config: dict[str, Any]) -> LdpMessageBody:
        return cls(type="SESSION_PROPOSE", config=config)

    @classmethod
    def session_accept(cls, session_id: str, negotiated_mode: PayloadMode) -> LdpMessageBody:
        return cls(type="SESSION_ACCEPT", session_id=session_id, negotiated_mode=negotiated_mode)

    @classmethod
    def session_reject(cls, reason: str | LdpError) -> LdpMessageBody:
        if isinstance(reason, str):
            error = LdpError.policy("SESSION_REJECTED", reason)
            return cls(type="SESSION_REJECT", reason=reason, error=error)
        else:
            return cls(type="SESSION_REJECT", reason=reason.message, error=reason)

    @classmethod
    def task_submit(cls, task_id: str, skill: str, input: Any) -> LdpMessageBody:
        return cls(type="TASK_SUBMIT", task_id=task_id, skill=skill, input=input)

    @classmethod
    def task_update(
        cls, task_id: str, progress: float | None = None, message: str | None = None
    ) -> LdpMessageBody:
        return cls(type="TASK_UPDATE", task_id=task_id, progress=progress, message=message)

    @classmethod
    def task_result(cls, task_id: str, output: Any, provenance: Provenance) -> LdpMessageBody:
        return cls(type="TASK_RESULT", task_id=task_id, output=output, provenance=provenance)

    @classmethod
    def task_failed(cls, task_id: str, error: str | LdpError) -> LdpMessageBody:
        if isinstance(error, str):
            error = LdpError.runtime("TASK_FAILED", error)
        return cls(type="TASK_FAILED", task_id=task_id, error=error)

    @classmethod
    def task_cancel(cls, task_id: str) -> LdpMessageBody:
        return cls(type="TASK_CANCEL", task_id=task_id)

    @classmethod
    def session_close(cls, reason: str | None = None) -> LdpMessageBody:
        return cls(type="SESSION_CLOSE", reason=reason)


class LdpEnvelope(BaseModel):
    """LDP message envelope — wraps every protocol message."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""
    body: LdpMessageBody
    payload_mode: PayloadMode = PayloadMode.TEXT
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    provenance: Provenance | None = None
    signature: str | None = None
    signature_algorithm: str | None = None

    model_config = {"populate_by_name": True}

    @classmethod
    def create(
        cls,
        session_id: str,
        from_id: str,
        to_id: str,
        body: LdpMessageBody,
        payload_mode: PayloadMode = PayloadMode.TEXT,
    ) -> LdpEnvelope:
        return cls(
            session_id=session_id,
            **{"from": from_id},
            to=to_id,
            body=body,
            payload_mode=payload_mode,
        )
