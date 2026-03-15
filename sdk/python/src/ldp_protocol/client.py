"""LDP HTTP client — discover delegates, manage sessions, submit tasks."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from ldp_protocol.types.identity import LdpIdentityCard
from ldp_protocol.types.messages import LdpEnvelope, LdpMessageBody
from ldp_protocol.types.payload import PayloadMode, negotiate_payload_mode
from ldp_protocol.types.provenance import Provenance
from ldp_protocol.types.session import LdpSession, SessionConfig, SessionState
from ldp_protocol.types.trust import TrustDomain


class LdpClient:
    """Async HTTP client for LDP protocol communication.

    Handles discovery, session management, and task submission.

    Usage:
        async with LdpClient() as client:
            identity = await client.discover("http://localhost:8090")
            result = await client.submit_task(
                "http://localhost:8090",
                skill="reasoning",
                input_data={"prompt": "Analyze..."},
            )
    """

    def __init__(
        self,
        delegate_id: str = "ldp:client:default",
        config: SessionConfig | None = None,
        timeout: float = 30.0,
        trust_domain: TrustDomain | None = None,
        enforce_trust_domains: bool = True,
    ):
        self.delegate_id = delegate_id
        self.config = config or SessionConfig()
        self.trust_domain = trust_domain or TrustDomain(name="default")
        self.enforce_trust_domains = enforce_trust_domains
        self._http = httpx.AsyncClient(timeout=timeout)
        self._sessions: dict[str, LdpSession] = {}

    async def __aenter__(self) -> LdpClient:
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    async def discover(self, url: str) -> LdpIdentityCard:
        """Fetch a delegate's identity card.

        Args:
            url: Base URL of the delegate (e.g., "http://localhost:8090").

        Returns:
            The delegate's identity card with full metadata.

        Raises:
            ConnectionError: If trust domain validation fails.
        """
        endpoint = f"{url.rstrip('/')}/ldp/identity"
        resp = await self._http.get(endpoint)
        resp.raise_for_status()
        identity = LdpIdentityCard.model_validate(resp.json())

        if self.enforce_trust_domains:
            if not self.trust_domain.trusts(identity.trust_domain.name):
                raise ConnectionError(
                    f"Trust domain '{identity.trust_domain.name}' "
                    f"is not trusted by '{self.trust_domain.name}'"
                )

        return identity

    async def discover_wellknown(self, url: str) -> LdpIdentityCard:
        """Discover a delegate via .well-known/ldp-identity convention.

        Tries .well-known first, falls back to /ldp/identity.
        """
        wellknown = f"{url.rstrip('/')}/.well-known/ldp-identity"
        try:
            resp = await self._http.get(wellknown)
            resp.raise_for_status()
            identity = LdpIdentityCard.model_validate(resp.json())
            # Only check trust here — fallback path checks in discover()
            if self.enforce_trust_domains:
                if not self.trust_domain.trusts(identity.trust_domain.name):
                    raise ConnectionError(
                        f"Trust domain '{identity.trust_domain.name}' "
                        f"is not trusted by '{self.trust_domain.name}'"
                    )
            return identity
        except Exception:
            return await self.discover(url)

    async def send_message(self, url: str, envelope: LdpEnvelope) -> LdpEnvelope:
        """Send an LDP message and receive a response."""
        endpoint = f"{url.rstrip('/')}/ldp/messages"
        resp = await self._http.post(
            endpoint,
            json=envelope.model_dump(by_alias=True),
        )
        resp.raise_for_status()
        return LdpEnvelope.model_validate(resp.json())

    async def establish_session(self, url: str) -> LdpSession:
        """Establish a new LDP session with a delegate.

        Performs the full handshake: HELLO -> CAPABILITY_MANIFEST ->
        SESSION_PROPOSE -> SESSION_ACCEPT.
        """
        # Step 1: HELLO
        hello = LdpEnvelope.create(
            session_id="",
            from_id=self.delegate_id,
            to_id=url,
            body=LdpMessageBody.hello(
                delegate_id=self.delegate_id,
                supported_modes=self.config.preferred_payload_modes,
            ),
        )
        hello_resp = await self.send_message(url, hello)

        # Step 2: SESSION_PROPOSE
        session_id = str(uuid4())
        propose = LdpEnvelope.create(
            session_id=session_id,
            from_id=self.delegate_id,
            to_id=url,
            body=LdpMessageBody.session_propose(
                config={
                    "preferred_payload_modes": [
                        m.value for m in self.config.preferred_payload_modes
                    ],
                    "ttl_secs": self.config.ttl_secs,
                    "trust_domain": self.trust_domain.name,
                }
            ),
        )
        propose_resp = await self.send_message(url, propose)

        if propose_resp.body.type == "SESSION_REJECT":
            raise ConnectionError(
                f"Session rejected: {propose_resp.body.reason}"
            )

        # Build session from response
        negotiated_mode = propose_resp.body.negotiated_mode or PayloadMode.TEXT
        identity = await self.discover(url)

        session = LdpSession(
            session_id=propose_resp.body.session_id or session_id,
            remote_url=url,
            remote_delegate_id=identity.delegate_id,
            state=SessionState.ACTIVE,
            trust_domain=identity.trust_domain,
            ttl_secs=self.config.ttl_secs,
        )
        session.payload.mode = negotiated_mode

        self._sessions[url] = session
        return session

    async def get_or_establish_session(self, url: str) -> LdpSession:
        """Get an existing session or establish a new one."""
        session = self._sessions.get(url)
        if session and session.is_active:
            return session
        return await self.establish_session(url)

    async def submit_task(
        self,
        url: str,
        *,
        skill: str,
        input_data: Any,
        session: LdpSession | None = None,
    ) -> dict[str, Any]:
        """Submit a task to a delegate and get the result.

        Args:
            url: Delegate URL.
            skill: Skill to invoke.
            input_data: Input data for the task.
            session: Optional existing session (auto-establishes if None).

        Returns:
            Dict with 'output' and 'provenance' keys.
        """
        if session is None:
            session = await self.get_or_establish_session(url)

        task_id = str(uuid4())
        submit = LdpEnvelope.create(
            session_id=session.session_id,
            from_id=self.delegate_id,
            to_id=session.remote_delegate_id,
            body=LdpMessageBody.task_submit(
                task_id=task_id,
                skill=skill,
                input=input_data,
            ),
            payload_mode=session.payload.mode,
        )

        response = await self.send_message(url, submit)
        session.touch()
        session.task_count += 1

        if response.body.type == "TASK_RESULT":
            return {
                "task_id": response.body.task_id,
                "output": response.body.output,
                "provenance": (
                    response.body.provenance.model_dump()
                    if response.body.provenance
                    else None
                ),
            }
        elif response.body.type == "TASK_FAILED":
            raise RuntimeError(f"Task failed: {response.body.error}")
        else:
            return {
                "task_id": task_id,
                "status": response.body.type,
                "message": response.body.message,
            }

    @property
    def active_sessions(self) -> int:
        """Number of active sessions."""
        return sum(1 for s in self._sessions.values() if s.is_active)
