"""Tests for LDP delegate base class."""
import pytest
from ldp_protocol.delegate import LdpDelegate
from ldp_protocol.types import (
    LdpCapability,
    LdpEnvelope,
    LdpMessageBody,
    PayloadMode,
    QualityMetrics,
    TrustDomain,
)


class EchoDelegate(LdpDelegate):
    async def handle_task(self, skill, input_data, task_id):
        return {"echo": input_data}, 0.99


def _make_delegate() -> EchoDelegate:
    return EchoDelegate(
        delegate_id="ldp:delegate:echo-test", name="Echo Test",
        model_family="test", model_version="1.0",
        capabilities=[LdpCapability(name="echo", quality=QualityMetrics(quality_score=0.99))],
    )


class TestDelegate:
    @pytest.mark.asyncio
    async def test_hello_returns_capability_manifest(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("", "client", "delegate",
            body=LdpMessageBody.hello("client", [PayloadMode.TEXT]))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "CAPABILITY_MANIFEST"

    @pytest.mark.asyncio
    async def test_session_propose_returns_accept(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody.session_propose(
                config={"preferred_payload_modes": ["text"], "ttl_secs": 3600, "trust_domain": "default"}))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_ACCEPT"

    @pytest.mark.asyncio
    async def test_task_submit_returns_result(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody.task_submit("t1", "echo", {"hello": "world"}))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_RESULT"
        assert resp.body.output == {"echo": {"hello": "world"}}
        assert resp.body.provenance is not None
        assert resp.body.provenance.confidence == 0.99

    @pytest.mark.asyncio
    async def test_task_cancel_returns_update(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody.task_cancel("t1"))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_UPDATE"
        assert resp.body.message == "cancelled"

    @pytest.mark.asyncio
    async def test_session_close_returns_ack(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody.session_close("done"))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_CLOSE"
        assert resp.body.reason == "acknowledged"

    @pytest.mark.asyncio
    async def test_unknown_message_returns_error(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody(type="UNKNOWN"))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_FAILED"

    def test_delegate_identity_card(self):
        delegate = _make_delegate()
        assert delegate.identity.delegate_id == "ldp:delegate:echo-test"
        assert delegate.identity.model_family == "test"
        assert len(delegate.identity.capabilities) == 1

    @pytest.mark.asyncio
    async def test_task_exception_returns_typed_error(self):
        class FailingDelegate(LdpDelegate):
            async def handle_task(self, skill, input_data, task_id):
                raise ValueError("Intentional test failure")

        delegate = FailingDelegate(
            delegate_id="ldp:delegate:fail", name="Failing",
            model_family="test", model_version="1.0",
        )
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody.task_submit("t1", "any", {}))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_FAILED"

    @pytest.mark.asyncio
    async def test_untrusted_domain_rejected(self):
        delegate = EchoDelegate(
            delegate_id="ldp:delegate:strict", name="Strict",
            model_family="test", model_version="1.0",
            trust_domain=TrustDomain(name="internal"),
        )
        env = LdpEnvelope.create("s1", "client", "delegate",
            body=LdpMessageBody.session_propose(
                config={"trust_domain": "external", "preferred_payload_modes": ["text"]}))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_REJECT"
