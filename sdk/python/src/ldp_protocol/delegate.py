"""LDP delegate base class — subclass to create a delegate server."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from ldp_protocol.types.capability import LdpCapability, QualityMetrics
from ldp_protocol.types.identity import LdpIdentityCard
from ldp_protocol.types.messages import LdpEnvelope, LdpMessageBody
from ldp_protocol.types.payload import PayloadMode, negotiate_payload_mode
from ldp_protocol.types.provenance import Provenance
from ldp_protocol.types.trust import TrustDomain


class LdpDelegate(ABC):
    """Base class for LDP delegates.

    Subclass and implement `handle_task` to create a delegate.

    Usage:
        class MyDelegate(LdpDelegate):
            async def handle_task(self, skill, input_data, task_id):
                return {"answer": "42"}, 0.95

        delegate = MyDelegate(
            delegate_id="ldp:delegate:my-agent",
            name="My Agent",
            model_family="claude",
            model_version="claude-sonnet-4-6",
            capabilities=[
                LdpCapability(
                    name="reasoning",
                    quality=QualityMetrics(quality_score=0.85, cost_per_call_usd=0.01),
                ),
            ],
        )

        # Run with Starlette (requires `pip install ldp-protocol[server]`):
        delegate.run(port=8090)
    """

    def __init__(
        self,
        *,
        delegate_id: str,
        name: str,
        model_family: str,
        model_version: str,
        capabilities: list[LdpCapability] | None = None,
        trust_domain: TrustDomain | None = None,
        context_window: int = 128000,
        reasoning_profile: str | None = None,
        cost_profile: str | None = None,
        supported_payload_modes: list[PayloadMode] | None = None,
        description: str | None = None,
        endpoint: str = "",
    ):
        self.identity = LdpIdentityCard(
            delegate_id=delegate_id,
            name=name,
            description=description,
            model_family=model_family,
            model_version=model_version,
            trust_domain=trust_domain or TrustDomain(name="default"),
            context_window=context_window,
            reasoning_profile=reasoning_profile,
            cost_profile=cost_profile,
            capabilities=capabilities or [],
            supported_payload_modes=supported_payload_modes
            or [PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
            endpoint=endpoint,
        )

    @abstractmethod
    async def handle_task(
        self, skill: str, input_data: Any, task_id: str
    ) -> tuple[Any, float]:
        """Handle a task and return (output, confidence).

        Args:
            skill: The skill being invoked.
            input_data: Input data from the task submission.
            task_id: Unique task identifier.

        Returns:
            Tuple of (output_data, confidence_score).
        """
        ...

    async def handle_message(self, envelope: LdpEnvelope) -> LdpEnvelope:
        """Route an incoming LDP message to the appropriate handler."""
        body = envelope.body

        if body.type == "HELLO":
            return self._handle_hello(envelope)
        elif body.type == "SESSION_PROPOSE":
            return self._handle_session_propose(envelope)
        elif body.type == "TASK_SUBMIT":
            return await self._handle_task_submit(envelope)
        elif body.type == "TASK_CANCEL":
            return self._handle_task_cancel(envelope)
        elif body.type == "SESSION_CLOSE":
            return self._handle_session_close(envelope)
        else:
            return LdpEnvelope.create(
                session_id=envelope.session_id,
                from_id=self.identity.delegate_id,
                to_id=envelope.from_,
                body=LdpMessageBody.task_failed(
                    task_id=body.task_id or "",
                    error=f"Unknown message type: {body.type}",
                ),
            )

    def _handle_hello(self, envelope: LdpEnvelope) -> LdpEnvelope:
        caps = [
            {"name": c.name, "description": c.description, "quality": c.quality.model_dump() if c.quality else None}
            for c in self.identity.capabilities
        ]
        return LdpEnvelope.create(
            session_id=envelope.session_id,
            from_id=self.identity.delegate_id,
            to_id=envelope.from_,
            body=LdpMessageBody.capability_manifest(capabilities=caps),
        )

    def _handle_session_propose(self, envelope: LdpEnvelope) -> LdpEnvelope:
        session_id = str(uuid4())
        # Negotiate payload mode
        initiator_modes = []
        if envelope.body.config and "preferred_payload_modes" in envelope.body.config:
            initiator_modes = [
                PayloadMode(m) for m in envelope.body.config["preferred_payload_modes"]
            ]
        negotiated = negotiate_payload_mode(
            initiator_modes, self.identity.supported_payload_modes
        )

        return LdpEnvelope.create(
            session_id=session_id,
            from_id=self.identity.delegate_id,
            to_id=envelope.from_,
            body=LdpMessageBody.session_accept(
                session_id=session_id,
                negotiated_mode=negotiated.mode,
            ),
        )

    async def _handle_task_submit(self, envelope: LdpEnvelope) -> LdpEnvelope:
        body = envelope.body
        task_id = body.task_id or str(uuid4())

        try:
            output, confidence = await self.handle_task(
                skill=body.skill or "",
                input_data=body.input,
                task_id=task_id,
            )

            provenance = Provenance.create(
                delegate_id=self.identity.delegate_id,
                model_version=self.identity.model_version,
                confidence=confidence,
                payload_mode_used=envelope.payload_mode,
                session_id=envelope.session_id,
            )

            return LdpEnvelope.create(
                session_id=envelope.session_id,
                from_id=self.identity.delegate_id,
                to_id=envelope.from_,
                body=LdpMessageBody.task_result(
                    task_id=task_id,
                    output=output,
                    provenance=provenance,
                ),
                payload_mode=envelope.payload_mode,
            )
        except Exception as e:
            return LdpEnvelope.create(
                session_id=envelope.session_id,
                from_id=self.identity.delegate_id,
                to_id=envelope.from_,
                body=LdpMessageBody.task_failed(task_id=task_id, error=str(e)),
            )

    def _handle_task_cancel(self, envelope: LdpEnvelope) -> LdpEnvelope:
        return LdpEnvelope.create(
            session_id=envelope.session_id,
            from_id=self.identity.delegate_id,
            to_id=envelope.from_,
            body=LdpMessageBody.task_update(
                task_id=envelope.body.task_id or "",
                message="cancelled",
            ),
        )

    def _handle_session_close(self, envelope: LdpEnvelope) -> LdpEnvelope:
        return LdpEnvelope.create(
            session_id=envelope.session_id,
            from_id=self.identity.delegate_id,
            to_id=envelope.from_,
            body=LdpMessageBody.session_close(reason="acknowledged"),
        )

    def run(self, host: str = "0.0.0.0", port: int = 8090) -> None:
        """Run the delegate as an HTTP server using Starlette + uvicorn.

        Requires: pip install ldp-protocol[server]
        """
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import JSONResponse
            from starlette.routing import Route
            import uvicorn
        except ImportError:
            raise ImportError(
                "Server dependencies not installed. Run: pip install ldp-protocol[server]"
            )

        identity = self.identity
        delegate = self

        async def handle_identity(request: Request) -> JSONResponse:
            return JSONResponse(identity.model_dump())

        async def handle_capabilities(request: Request) -> JSONResponse:
            caps = [c.model_dump() for c in identity.capabilities]
            return JSONResponse({"capabilities": caps})

        async def handle_messages(request: Request) -> JSONResponse:
            data = await request.json()
            envelope = LdpEnvelope.model_validate(data)
            response = await delegate.handle_message(envelope)
            return JSONResponse(response.model_dump(by_alias=True))

        app = Starlette(
            routes=[
                Route("/ldp/identity", handle_identity, methods=["GET"]),
                Route("/ldp/capabilities", handle_capabilities, methods=["GET"]),
                Route("/ldp/messages", handle_messages, methods=["POST"]),
            ],
        )

        self.identity.endpoint = f"http://{host}:{port}"
        print(f"LDP Delegate '{identity.name}' starting on {host}:{port}")
        print(f"  ID: {identity.delegate_id}")
        print(f"  Model: {identity.model_family} {identity.model_version}")
        print(f"  Skills: {[c.name for c in identity.capabilities]}")
        uvicorn.run(app, host=host, port=port)
