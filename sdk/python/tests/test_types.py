"""Tests for LDP protocol types."""

from ldp_protocol.types import (
    LdpCapability,
    LdpEnvelope,
    LdpIdentityCard,
    LdpMessageBody,
    NegotiatedPayload,
    PayloadMode,
    Provenance,
    QualityMetrics,
    SessionConfig,
    TrustDomain,
    negotiate_payload_mode,
)
from ldp_protocol.types.capability import ClaimType
from ldp_protocol.types.error import ErrorSeverity, FailureCategory, LdpError


class TestPayloadMode:
    def test_mode_numbers(self):
        assert PayloadMode.TEXT.mode_number == 0
        assert PayloadMode.SEMANTIC_FRAME.mode_number == 1
        assert PayloadMode.EMBEDDING_HINTS.mode_number == 2
        assert PayloadMode.SEMANTIC_GRAPH.mode_number == 3

    def test_is_implemented(self):
        assert PayloadMode.TEXT.is_implemented
        assert PayloadMode.SEMANTIC_FRAME.is_implemented
        assert not PayloadMode.EMBEDDING_HINTS.is_implemented
        assert not PayloadMode.SEMANTIC_GRAPH.is_implemented


class TestPayloadNegotiation:
    def test_both_support_semantic_frame(self):
        result = negotiate_payload_mode(
            [PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
            [PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
        )
        assert result.mode == PayloadMode.SEMANTIC_FRAME
        assert result.fallback_chain == [PayloadMode.TEXT]

    def test_falls_back_to_text(self):
        result = negotiate_payload_mode(
            [PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
            [PayloadMode.TEXT],
        )
        assert result.mode == PayloadMode.TEXT
        assert result.fallback_chain == []

    def test_empty_prefs_default_to_text(self):
        result = negotiate_payload_mode([], [])
        assert result.mode == PayloadMode.TEXT

    def test_skips_unimplemented_modes(self):
        result = negotiate_payload_mode(
            [PayloadMode.SEMANTIC_GRAPH, PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
            [PayloadMode.SEMANTIC_GRAPH, PayloadMode.TEXT],
        )
        assert result.mode == PayloadMode.TEXT


class TestTrustDomain:
    def test_same_domain_trusted(self):
        domain = TrustDomain(name="acme-prod")
        assert domain.trusts("acme-prod")

    def test_cross_domain_denied_by_default(self):
        domain = TrustDomain(name="acme-prod")
        assert not domain.trusts("external")

    def test_cross_domain_with_explicit_peer(self):
        domain = TrustDomain(
            name="acme-prod",
            allow_cross_domain=True,
            trusted_peers=["partner-corp"],
        )
        assert domain.trusts("partner-corp")
        assert not domain.trusts("unknown-corp")

    def test_mutual_trust_both_sides(self):
        domain_a = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=["partner"])
        domain_b = TrustDomain(name="partner", allow_cross_domain=True, trusted_peers=["acme"])
        assert domain_a.mutually_trusts(domain_b)

    def test_mutual_trust_one_sided_fails(self):
        domain_a = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=["partner"])
        domain_c = TrustDomain(name="partner", allow_cross_domain=True, trusted_peers=[])
        assert not domain_a.mutually_trusts(domain_c)

    def test_same_domain_mutual_trust(self):
        domain = TrustDomain(name="acme")
        other = TrustDomain(name="acme")
        assert domain.mutually_trusts(other)

    def test_empty_trust_domain_name_rejected(self):
        import pytest
        with pytest.raises(Exception):
            TrustDomain(name="")

    def test_empty_trusted_peers_blocks_cross_domain(self):
        domain = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=[])
        assert not domain.trusts("anyone")

    def test_allow_cross_domain_false_blocks_even_listed_peer(self):
        domain = TrustDomain(name="acme", allow_cross_domain=False, trusted_peers=["partner"])
        assert not domain.trusts("partner")

    def test_trust_domain_serialization(self):
        domain = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=["a", "b"])
        data = domain.model_dump()
        restored = TrustDomain.model_validate(data)
        assert restored.trusts("a")
        assert restored.trusts("b")
        assert not restored.trusts("c")


class TestIdentityCard:
    def _make_card(self) -> LdpIdentityCard:
        return LdpIdentityCard(
            delegate_id="ldp:delegate:test",
            name="Test Agent",
            model_family="claude",
            model_version="claude-sonnet-4-6",
            trust_domain=TrustDomain(name="test"),
            context_window=128000,
            capabilities=[
                LdpCapability(
                    name="reasoning",
                    quality=QualityMetrics(
                        quality_score=0.85,
                        cost_per_call_usd=0.01,
                        latency_p50_ms=1200,
                    ),
                ),
                LdpCapability(name="summarization"),
            ],
        )

    def test_capability_lookup(self):
        card = self._make_card()
        assert card.capability("reasoning") is not None
        assert card.capability("nonexistent") is None

    def test_quality_score(self):
        card = self._make_card()
        assert card.quality_score("reasoning") == 0.85
        assert card.quality_score("summarization") == 0.0
        assert card.quality_score("nonexistent") == 0.0

    def test_cost(self):
        card = self._make_card()
        assert card.cost("reasoning") == 0.01
        assert card.cost("summarization") == float("inf")

    def test_latency(self):
        card = self._make_card()
        assert card.latency("reasoning") == 1200

    def test_serialization_roundtrip(self):
        card = self._make_card()
        data = card.model_dump()
        restored = LdpIdentityCard.model_validate(data)
        assert restored.delegate_id == card.delegate_id
        assert restored.quality_score("reasoning") == 0.85


class TestProvenance:
    def test_create(self):
        p = Provenance.create("ldp:delegate:test", "v1.0", confidence=0.9)
        assert p.produced_by == "ldp:delegate:test"
        assert p.model_version == "v1.0"
        assert p.confidence == 0.9
        assert p.verified is False
        assert p.timestamp is not None


class TestMessages:
    def test_hello(self):
        body = LdpMessageBody.hello("ldp:delegate:test", [PayloadMode.TEXT])
        assert body.type == "HELLO"
        assert body.delegate_id == "ldp:delegate:test"

    def test_task_submit(self):
        body = LdpMessageBody.task_submit("task-1", "reasoning", {"prompt": "test"})
        assert body.type == "TASK_SUBMIT"
        assert body.task_id == "task-1"
        assert body.skill == "reasoning"

    def test_task_result(self):
        prov = Provenance.create("ldp:delegate:test", "v1.0")
        body = LdpMessageBody.task_result("task-1", {"answer": "42"}, prov)
        assert body.type == "TASK_RESULT"
        assert body.output == {"answer": "42"}
        assert body.provenance is not None

    def test_envelope_create(self):
        body = LdpMessageBody.hello("test", [PayloadMode.TEXT])
        env = LdpEnvelope.create("sess-1", "from-id", "to-id", body)
        assert env.session_id == "sess-1"
        assert env.body.type == "HELLO"
        assert env.message_id  # auto-generated

    def test_envelope_serialization(self):
        body = LdpMessageBody.task_submit("t1", "echo", {"data": 1})
        env = LdpEnvelope.create("s1", "a", "b", body)
        data = env.model_dump(by_alias=True)
        assert "from" in data  # alias works
        restored = LdpEnvelope.model_validate(data)
        assert restored.body.task_id == "t1"


class TestClaimType:
    def test_default_is_self_claimed(self):
        metrics = QualityMetrics()
        assert metrics.claim_type == ClaimType.SELF_CLAIMED

    def test_serialization_roundtrip(self):
        metrics = QualityMetrics(
            quality_score=0.95,
            claim_type=ClaimType.ISSUER_ATTESTED,
        )
        data = metrics.model_dump()
        assert data["claim_type"] == "issuer_attested"
        restored = QualityMetrics.model_validate(data)
        assert restored.claim_type == ClaimType.ISSUER_ATTESTED

    def test_all_claim_types(self):
        assert ClaimType.SELF_CLAIMED
        assert ClaimType.ISSUER_ATTESTED
        assert ClaimType.RUNTIME_OBSERVED
        assert ClaimType.EXTERNALLY_BENCHMARKED


class TestLdpError:
    def test_identity_error(self):
        err = LdpError.identity("IDENTITY_MISMATCH", "Trust domain mismatch")
        assert err.category == FailureCategory.IDENTITY
        assert not err.retryable

    def test_runtime_retryable(self):
        err = LdpError.runtime("TIMEOUT", "Timed out")
        assert err.retryable

    def test_partial_output(self):
        err = LdpError.runtime("TIMEOUT", "Timed out")
        err.partial_output = {"partial": "data"}
        assert err.partial_output == {"partial": "data"}

    def test_serialization(self):
        err = LdpError.capability("SKILL_NOT_FOUND", "No such skill")
        data = err.model_dump()
        restored = LdpError.model_validate(data)
        assert restored.code == "SKILL_NOT_FOUND"

    def test_policy_fatal(self):
        err = LdpError.policy("TRUST_VIOLATION", "Not allowed")
        assert err.severity == ErrorSeverity.FATAL

    def test_quality_constructor(self):
        err = LdpError.quality("BELOW_THRESHOLD", "Too low")
        assert err.category == FailureCategory.QUALITY

    def test_session_constructor(self):
        err = LdpError.session("SESSION_EXPIRED", "Session timed out")
        assert err.category == FailureCategory.SESSION
        assert err.retryable

    def test_transport_constructor(self):
        err = LdpError.transport("CONNECTION_LOST", "Lost connection")
        assert err.category == FailureCategory.TRANSPORT
        assert err.severity == ErrorSeverity.WARNING
        assert err.retryable

    def test_task_failed_with_string_creates_typed_error(self):
        body = LdpMessageBody.task_failed("task-1", "something went wrong")
        assert body.type == "TASK_FAILED"
        assert isinstance(body.error, LdpError)
        assert body.error.code == "TASK_FAILED"
        assert body.error.message == "something went wrong"

    def test_task_failed_with_ldp_error(self):
        err = LdpError.runtime("TIMEOUT", "Timed out")
        body = LdpMessageBody.task_failed("task-1", err)
        assert isinstance(body.error, LdpError)
        assert body.error.code == "TIMEOUT"

    def test_session_reject_with_string_creates_typed_error(self):
        body = LdpMessageBody.session_reject("not trusted")
        assert body.type == "SESSION_REJECT"
        assert body.reason == "not trusted"
        assert isinstance(body.error, LdpError)
        assert body.error.category == FailureCategory.POLICY

    def test_session_reject_with_ldp_error(self):
        err = LdpError.policy("TRUST_VIOLATION", "Domain not trusted")
        body = LdpMessageBody.session_reject(err)
        assert body.reason == "Domain not trusted"
        assert body.error.code == "TRUST_VIOLATION"
