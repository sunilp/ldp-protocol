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
    register_payload_mode,
)


class EchoDelegate(LdpDelegate):
    async def handle_task(self, skill, input_data, task_id):
        return {"echo": input_data}, 0.99


def _make_delegate() -> EchoDelegate:
    return EchoDelegate(
        delegate_id="ldp:delegate:echo-test",
        name="Echo Test",
        model_family="test",
        model_version="1.0",
        capabilities=[LdpCapability(name="echo", quality=QualityMetrics(quality_score=0.99))],
    )


class TestDelegate:
    @pytest.mark.asyncio
    async def test_hello_returns_capability_manifest(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "", "client", "delegate", body=LdpMessageBody.hello("client", [PayloadMode.TEXT])
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "CAPABILITY_MANIFEST"

    @pytest.mark.asyncio
    async def test_session_propose_returns_accept(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={
                    "preferred_payload_modes": ["text"],
                    "ttl_secs": 3600,
                    "trust_domain": "default",
                }
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_ACCEPT"

    @pytest.mark.asyncio
    async def test_task_submit_returns_result(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.task_submit("t1", "echo", {"hello": "world"}),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_RESULT"
        assert resp.body.output == {"echo": {"hello": "world"}}
        assert resp.body.provenance is not None
        assert resp.body.provenance.confidence == 0.99

    @pytest.mark.asyncio
    async def test_task_cancel_returns_update(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate", body=LdpMessageBody.task_cancel("t1"))
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_UPDATE"
        assert resp.body.message == "cancelled"

    @pytest.mark.asyncio
    async def test_session_close_returns_ack(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "s1", "client", "delegate", body=LdpMessageBody.session_close("done")
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_CLOSE"
        assert resp.body.reason == "acknowledged"

    @pytest.mark.asyncio
    async def test_unknown_message_returns_error(self):
        delegate = _make_delegate()
        env = LdpEnvelope.create("s1", "client", "delegate", body=LdpMessageBody(type="UNKNOWN"))
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
            delegate_id="ldp:delegate:fail",
            name="Failing",
            model_family="test",
            model_version="1.0",
        )
        env = LdpEnvelope.create(
            "s1", "client", "delegate", body=LdpMessageBody.task_submit("t1", "any", {})
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "TASK_FAILED"

    @pytest.mark.asyncio
    async def test_untrusted_domain_rejected(self):
        delegate = EchoDelegate(
            delegate_id="ldp:delegate:strict",
            name="Strict",
            model_family="test",
            model_version="1.0",
            trust_domain=TrustDomain(name="internal"),
        )
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={"trust_domain": "external", "preferred_payload_modes": ["text"]}
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_REJECT"


def _graph_delegate(delegate_id: str) -> EchoDelegate:
    """An EchoDelegate that declares all modes including SEMANTIC_GRAPH."""
    return EchoDelegate(
        delegate_id=delegate_id,
        name="Graph",
        model_family="test",
        model_version="1.0",
        supported_payload_modes=[
            PayloadMode.SEMANTIC_GRAPH,
            PayloadMode.SEMANTIC_FRAME,
            PayloadMode.TEXT,
        ],
    )


def _propose_all_modes() -> LdpEnvelope:
    return LdpEnvelope.create(
        "s1",
        "client",
        "delegate",
        body=LdpMessageBody.session_propose(
            config={
                "preferred_payload_modes": ["semantic_graph", "semantic_frame", "text"],
                "trust_domain": "default",
            }
        ),
    )


class TestMode3Negotiation:
    @pytest.mark.asyncio
    async def test_registered_delegate_negotiates_mode_3(self):
        # Responder declares SEMANTIC_GRAPH *and* has a registered codec for
        # it → it advertises Mode 3, and an initiator that wants it lands there.
        register_payload_mode(PayloadMode.SEMANTIC_GRAPH)
        delegate = _graph_delegate("ldp:delegate:graph")
        resp = await delegate.handle_message(_propose_all_modes())
        assert resp.body.type == "SESSION_ACCEPT"
        assert resp.body.negotiated_mode == PayloadMode.SEMANTIC_GRAPH

    @pytest.mark.asyncio
    async def test_unregistered_delegate_falls_back(self):
        # Same declaration, but no codec registered → SEMANTIC_GRAPH is not
        # advertised, so negotiation honestly falls back to the best shared
        # mode (SEMANTIC_FRAME) instead of claiming a codec it doesn't have.
        delegate = _graph_delegate("ldp:delegate:no-graph")
        resp = await delegate.handle_message(_propose_all_modes())
        assert resp.body.type == "SESSION_ACCEPT"
        assert resp.body.negotiated_mode == PayloadMode.SEMANTIC_FRAME

    @pytest.mark.asyncio
    async def test_unknown_mode_string_does_not_crash(self):
        # A forward-compat / malformed peer sending an unknown mode string must
        # not crash the handler — the unknown mode is skipped and negotiation
        # proceeds on the shared known modes.
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={
                    "preferred_payload_modes": ["wormhole_mode", "text"],
                    "trust_domain": "default",
                }
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_ACCEPT"
        assert resp.body.negotiated_mode == PayloadMode.TEXT

    @pytest.mark.asyncio
    async def test_non_string_mode_does_not_crash(self):
        # A malformed peer may put non-string (here, unhashable) entries in
        # preferred_payload_modes. The set-membership filter raises TypeError on
        # an unhashable item, so non-strings must be dropped before the check —
        # the handler skips them and negotiates down to a shared known mode
        # instead of crashing on untrusted wire input.
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={
                    "preferred_payload_modes": [
                        {"mode": "semantic_graph"},
                        ["text"],
                        "text",
                    ],
                    "trust_domain": "default",
                }
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_ACCEPT"
        assert resp.body.negotiated_mode == PayloadMode.TEXT

    @pytest.mark.asyncio
    async def test_non_list_modes_does_not_crash(self):
        # preferred_payload_modes itself is untrusted wire input (Any). A peer
        # sending a non-iterable scalar would raise TypeError on `for m in ...`
        # and escape as an unhandled 500; a non-list is treated as "no
        # preference expressed" and negotiation falls to the TEXT floor.
        delegate = _make_delegate()
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={
                    "preferred_payload_modes": 3,
                    "trust_domain": "default",
                }
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_ACCEPT"
        assert resp.body.negotiated_mode == PayloadMode.TEXT

    def test_advertised_identity_filters_unregistered_modes(self):
        delegate = _graph_delegate("ldp:delegate:adv-id")
        # The advertised (served) card narrows to modes it can actually speak,
        assert delegate.advertised_identity().supported_payload_modes == [
            PayloadMode.SEMANTIC_FRAME,
            PayloadMode.TEXT,
        ]
        # while the delegate's own identity keeps the full declared intent.
        assert PayloadMode.SEMANTIC_GRAPH in delegate.identity.supported_payload_modes

    def test_advertised_identity_includes_registered_mode(self):
        register_payload_mode(PayloadMode.SEMANTIC_GRAPH)
        delegate = _graph_delegate("ldp:delegate:adv-id2")
        assert delegate.advertised_identity().supported_payload_modes == [
            PayloadMode.SEMANTIC_GRAPH,
            PayloadMode.SEMANTIC_FRAME,
            PayloadMode.TEXT,
        ]


class TestLifecycleHooks:
    @pytest.mark.asyncio
    async def test_on_session_start_fires_on_accept(self):
        events = []

        class HookDelegate(EchoDelegate):
            def on_session_start(self, session_id, negotiated):
                events.append((session_id, negotiated.mode))

        delegate = HookDelegate(
            delegate_id="ldp:delegate:hook-start",
            name="Hook",
            model_family="test",
            model_version="1.0",
        )
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={"preferred_payload_modes": ["text"], "trust_domain": "default"}
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_ACCEPT"
        assert len(events) == 1
        # session_id is the freshly minted accept id, mode is what was agreed.
        assert events[0][0] == resp.body.session_id
        assert events[0][1] == PayloadMode.TEXT

    @pytest.mark.asyncio
    async def test_on_session_start_not_fired_on_reject(self):
        events = []

        class HookDelegate(EchoDelegate):
            def on_session_start(self, session_id, negotiated):
                events.append(session_id)

        delegate = HookDelegate(
            delegate_id="ldp:delegate:hook-strict",
            name="HookStrict",
            model_family="test",
            model_version="1.0",
            trust_domain=TrustDomain(name="internal"),
        )
        env = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={"trust_domain": "external", "preferred_payload_modes": ["text"]}
            ),
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_REJECT"
        assert events == []

    @pytest.mark.asyncio
    async def test_on_session_end_fires_on_close_with_reason(self):
        events = []

        class HookDelegate(EchoDelegate):
            def on_session_end(self, session_id, reason):
                events.append((session_id, reason))

        delegate = HookDelegate(
            delegate_id="ldp:delegate:hook-end",
            name="HookEnd",
            model_family="test",
            model_version="1.0",
        )
        env = LdpEnvelope.create(
            "sess-9", "client", "delegate", body=LdpMessageBody.session_close("client done")
        )
        resp = await delegate.handle_message(env)
        assert resp.body.type == "SESSION_CLOSE"
        assert events == [("sess-9", "client done")]

    @pytest.mark.asyncio
    async def test_default_hooks_are_noops(self):
        # The base delegate overrides no hooks; the happy path must not error.
        delegate = _make_delegate()
        propose = LdpEnvelope.create(
            "s1",
            "client",
            "delegate",
            body=LdpMessageBody.session_propose(
                config={"preferred_payload_modes": ["text"], "trust_domain": "default"}
            ),
        )
        assert (await delegate.handle_message(propose)).body.type == "SESSION_ACCEPT"
        close = LdpEnvelope.create(
            "s1", "client", "delegate", body=LdpMessageBody.session_close("done")
        )
        assert (await delegate.handle_message(close)).body.type == "SESSION_CLOSE"
