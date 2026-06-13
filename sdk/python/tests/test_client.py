"""Tests for LDP client honesty.

A client must only *propose* payload modes it can actually speak — the
initiator-side mirror of the responder-side advertising honesty in
LdpDelegate. Network calls are stubbed so establish_session runs offline.
"""

import pytest

from ldp_protocol.client import LdpClient
from ldp_protocol.types import (
    LdpEnvelope,
    LdpIdentityCard,
    LdpMessageBody,
    PayloadMode,
    SessionConfig,
    TrustDomain,
    register_payload_mode,
)


def _stub_network(
    monkeypatch, sent: list, accept_mode: PayloadMode = PayloadMode.SEMANTIC_FRAME
) -> None:
    """Replace the client's network calls so establish_session runs offline."""

    async def fake_send(self, url, envelope):
        sent.append(envelope)
        if envelope.body.type == "SESSION_PROPOSE":
            return LdpEnvelope.create(
                "sess",
                "delegate",
                "client",
                body=LdpMessageBody.session_accept("sess", accept_mode),
            )
        return LdpEnvelope.create(
            "sess",
            "delegate",
            "client",
            body=LdpMessageBody.capability_manifest({"capabilities": []}),
        )

    async def fake_discover(self, url):
        return LdpIdentityCard(
            delegate_id="ldp:delegate:remote",
            name="Remote",
            model_family="test",
            model_version="1.0",
            trust_domain=TrustDomain(name="default"),
            context_window=128000,
        )

    monkeypatch.setattr(LdpClient, "send_message", fake_send)
    monkeypatch.setattr(LdpClient, "discover", fake_discover)


def _proposed_modes(sent: list) -> list[str]:
    propose = next(e for e in sent if e.body.type == "SESSION_PROPOSE")
    return propose.body.config["preferred_payload_modes"]


def _client() -> LdpClient:
    return LdpClient(
        config=SessionConfig(
            preferred_payload_modes=[
                PayloadMode.SEMANTIC_GRAPH,
                PayloadMode.SEMANTIC_FRAME,
                PayloadMode.TEXT,
            ]
        )
    )


class TestClientAdvertisingHonesty:
    @pytest.mark.asyncio
    async def test_client_does_not_propose_unregistered_mode(self, monkeypatch):
        sent: list = []
        _stub_network(monkeypatch, sent)
        client = _client()
        try:
            await client.establish_session("http://remote")
        finally:
            await client.close()
        # No codec registered for SEMANTIC_GRAPH → the client must not propose
        # a mode it cannot encode, even though it is in its configured prefs.
        assert _proposed_modes(sent) == ["semantic_frame", "text"]

    @pytest.mark.asyncio
    async def test_client_proposes_registered_mode(self, monkeypatch):
        register_payload_mode(PayloadMode.SEMANTIC_GRAPH)
        sent: list = []
        _stub_network(monkeypatch, sent, accept_mode=PayloadMode.SEMANTIC_GRAPH)
        client = _client()
        try:
            await client.establish_session("http://remote")
        finally:
            await client.close()
        # With a codec registered, the client honestly proposes Mode 3 — and
        # accepts it back, since it is now in the client's advertised set.
        assert _proposed_modes(sent) == ["semantic_graph", "semantic_frame", "text"]

    @pytest.mark.asyncio
    async def test_client_rejects_unspeakable_negotiated_mode(self, monkeypatch):
        # A responder returns a mode the client never advertised and cannot
        # encode → the handshake is refused, not silently committed to.
        sent: list = []
        _stub_network(monkeypatch, sent, accept_mode=PayloadMode.SEMANTIC_GRAPH)
        client = _client()  # SEMANTIC_GRAPH not registered → not advertised
        try:
            # Assert the contract-violation message specifically, so the test
            # verifies the advertise/encode rejection rather than any incidental
            # ConnectionError on the way to the handshake.
            with pytest.raises(ConnectionError, match=r"did not advertise and cannot encode"):
                await client.establish_session("http://remote")
        finally:
            await client.close()
