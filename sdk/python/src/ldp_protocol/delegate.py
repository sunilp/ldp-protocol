"""LDP delegate base class — subclass to create a delegate server."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from ldp_protocol.types.capability import LdpCapability
from ldp_protocol.types.error import LdpError
from ldp_protocol.types.identity import LdpIdentityCard
from ldp_protocol.types.messages import LdpEnvelope, LdpMessageBody
from ldp_protocol.types.payload import NegotiatedPayload, PayloadMode, negotiate_payload_mode
from ldp_protocol.types.provenance import Provenance
from ldp_protocol.types.trust import TrustDomain
from ldp_protocol.types.verification import VerificationStatus


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
        signing_secret: str | None = None,
    ):
        self.signing_secret = signing_secret
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
    async def handle_task(self, skill: str, input_data: Any, task_id: str) -> tuple[Any, float]:
        """Handle a task and return (output, confidence).

        Args:
            skill: The skill being invoked.
            input_data: Input data from the task submission.
            task_id: Unique task identifier.

        Returns:
            Tuple of (output_data, confidence_score).
        """
        ...

    # ------------------------------------------------------------------
    # Lifecycle hooks — override to react to session / mode transitions.
    #
    # Default implementations are no-ops, so a subclass opts in only to the
    # transitions it cares about without overriding core protocol logic.
    # These run SYNCHRONOUSLY inside the protocol response path; keep an
    # override fast and non-throwing — a hook that raises aborts the in-flight
    # SESSION_ACCEPT / SESSION_CLOSE (fail-loud, by design).
    # ------------------------------------------------------------------

    def on_session_start(self, session_id: str, negotiated: NegotiatedPayload) -> None:
        """Called when a session has been accepted and a payload mode agreed.

        Fires from ``_handle_session_propose`` after SESSION_ACCEPT is built,
        with the freshly-minted session id the accept carries back. Override
        to set up per-session state, logging, metrics, etc.
        """

    def on_mode_change(self, session_id: str, old_mode: PayloadMode, new_mode: PayloadMode) -> None:
        """NOT YET CALLED BY CORE — overriding this has no effect in v1.

        This is the designated reaction point for mid-session mode transitions
        (adaptive degradation, per-message fallback). The v1 contract Sunil set
        in #14 is per-message fallback + re-negotiate-from-scratch, and adaptive
        degradation is explicitly v-next — so the core does not emit a
        mid-session mode change yet. The signature is provided now (per his
        "propose signatures alongside the #15 work" invitation) so that
        implementations and future SDK versions have a stable hook to call;
        core wiring lands with the adaptive-degradation work.
        """

    def on_session_end(self, session_id: str, reason: str) -> None:
        """Called when a session is closed.

        Fires from ``_handle_session_close`` when a SESSION_CLOSE is handled.
        Override to tear down per-session state, flush metrics, etc. (Note: the
        bundled ``LdpClient`` does not send SESSION_CLOSE, so today this fires
        only for external/manual closers.)
        """

    def advertised_identity(self) -> LdpIdentityCard:
        """This delegate's identity card with payload modes narrowed to the
        ones it can actually speak in this process.

        Publish THIS anywhere the card goes to peers (the discovery endpoint,
        capability exchange) so the advertised modes match what negotiation
        will honestly agree to. ``self.identity`` keeps the full declared
        intent; this is the honest on-the-wire view of it.
        """
        return self.identity.model_copy(
            update={"supported_payload_modes": self.identity.advertised_payload_modes()}
        )

    async def handle_message(self, envelope: LdpEnvelope) -> LdpEnvelope:
        """Route an incoming LDP message to the appropriate handler."""
        # Verify signature if signing is configured
        if self.signing_secret:
            from ldp_protocol.signing import verify_envelope as verify_sig, apply_signature

            if envelope.signature:
                if not verify_sig(envelope, self.signing_secret, envelope.signature):
                    return LdpEnvelope.create(
                        session_id=envelope.session_id,
                        from_id=self.identity.delegate_id,
                        to_id=envelope.from_,
                        body=LdpMessageBody.task_failed(
                            task_id=envelope.body.task_id or "",
                            error="Invalid message signature",
                        ),
                    )

        body = envelope.body

        if body.type == "HELLO":
            response = self._handle_hello(envelope)
        elif body.type == "SESSION_PROPOSE":
            response = self._handle_session_propose(envelope)
        elif body.type == "TASK_SUBMIT":
            response = await self._handle_task_submit(envelope)
        elif body.type == "TASK_CANCEL":
            response = self._handle_task_cancel(envelope)
        elif body.type == "SESSION_CLOSE":
            response = self._handle_session_close(envelope)
        else:
            response = LdpEnvelope.create(
                session_id=envelope.session_id,
                from_id=self.identity.delegate_id,
                to_id=envelope.from_,
                body=LdpMessageBody.task_failed(
                    task_id=body.task_id or "",
                    error=f"Unknown message type: {body.type}",
                ),
            )

        # Sign outgoing response
        if self.signing_secret:
            from ldp_protocol.signing import apply_signature

            apply_signature(response, self.signing_secret)

        return response

    def _handle_hello(self, envelope: LdpEnvelope) -> LdpEnvelope:
        caps = [
            {
                "name": c.name,
                "description": c.description,
                "quality": c.quality.model_dump() if c.quality else None,
            }
            for c in self.identity.capabilities
        ]
        return LdpEnvelope.create(
            session_id=envelope.session_id,
            from_id=self.identity.delegate_id,
            to_id=envelope.from_,
            body=LdpMessageBody.capability_manifest(capabilities=caps),
        )

    def _handle_session_propose(self, envelope: LdpEnvelope) -> LdpEnvelope:
        # Validate trust domain
        remote_domain = "unknown"
        if envelope.body.config and "trust_domain" in envelope.body.config:
            remote_domain = envelope.body.config["trust_domain"]

        if not self.identity.trust_domain.trusts(remote_domain):
            return LdpEnvelope.create(
                session_id=envelope.session_id,
                from_id=self.identity.delegate_id,
                to_id=envelope.from_,
                body=LdpMessageBody.session_reject(
                    reason=f"Trust domain '{remote_domain}' not trusted by '{self.identity.trust_domain.name}'"
                ),
            )

        session_id = str(uuid4())
        # Negotiate payload mode. `config` is untrusted wire input
        # (dict[str, Any], unvalidated), so both the preferred-modes list AND its
        # items may be malformed. Treat a non-list as "no preference expressed"
        # and drop non-string / unknown / forward-compat items, so a Mode-3-aware
        # peer and an older peer still negotiate down to a shared known mode
        # instead of crashing the handler — a non-iterable would raise on
        # iteration, and an unhashable item would raise on the membership check.
        initiator_modes = []
        if envelope.body.config:
            raw_modes = envelope.body.config.get("preferred_payload_modes")
            if isinstance(raw_modes, list):
                valid_modes = {mode.value for mode in PayloadMode}
                initiator_modes = [
                    PayloadMode(m) for m in raw_modes if isinstance(m, str) and m in valid_modes
                ]
        negotiated = negotiate_payload_mode(
            initiator_modes, self.identity.advertised_payload_modes()
        )

        accept = LdpEnvelope.create(
            session_id=session_id,
            from_id=self.identity.delegate_id,
            to_id=envelope.from_,
            body=LdpMessageBody.session_accept(
                session_id=session_id,
                negotiated_mode=negotiated.mode,
            ),
        )

        self.on_session_start(session_id, negotiated)

        return accept

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
                verification_status=VerificationStatus.SELF_VERIFIED,
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
                body=LdpMessageBody.task_failed(
                    task_id=task_id,
                    error=LdpError.runtime("TASK_EXECUTION_ERROR", str(e)),
                ),
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
        self.on_session_end(envelope.session_id, envelope.body.reason or "")
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
            # Serve the honest, advertised view (modes narrowed to installed
            # codecs) so discovery agrees with what negotiation will accept.
            return JSONResponse(delegate.advertised_identity().model_dump())

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
                Route("/.well-known/ldp-identity", handle_identity, methods=["GET"]),
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
