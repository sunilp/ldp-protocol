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


from ldp_protocol.types.contract import (
    DelegationContract, PolicyEnvelope, FailurePolicy, BudgetPolicy,
)


class TestDelegationContract:
    def test_contract_creation(self):
        c = DelegationContract(objective="Summarize", success_criteria=["<=300 words"])
        assert c.contract_id
        assert c.objective == "Summarize"
        assert c.deadline is None

    def test_contract_with_budget(self):
        c = DelegationContract(
            objective="task", success_criteria=[],
            policy=PolicyEnvelope(budget=BudgetPolicy(max_tokens=5000, max_cost_usd=0.05)),
        )
        assert c.policy.budget.max_tokens == 5000

    def test_default_failure_policy(self):
        c = DelegationContract(objective="task", success_criteria=[])
        assert c.policy.failure_policy == FailurePolicy.FAIL_OPEN

    def test_serialization_roundtrip(self):
        c = DelegationContract(
            objective="Analyze", success_criteria=["accuracy > 0.9"],
            policy=PolicyEnvelope(
                failure_policy=FailurePolicy.FAIL_CLOSED,
                budget=BudgetPolicy(max_tokens=10000),
            ),
            deadline="2026-06-01T00:00:00Z",
        )
        data = c.model_dump()
        restored = DelegationContract.model_validate(data)
        assert restored.objective == "Analyze"
        assert restored.policy.failure_policy == FailurePolicy.FAIL_CLOSED

    def test_policy_envelope_defaults(self):
        p = PolicyEnvelope()
        assert p.failure_policy == FailurePolicy.FAIL_OPEN
        assert p.budget is None
        assert p.safety_constraints == []

    def test_contract_no_budget_no_deadline(self):
        c = DelegationContract(objective="Draft ideas", success_criteria=["be creative"])
        assert c.policy.budget is None
        assert c.deadline is None


class TestProvenanceContract:
    def test_provenance_has_contract_fields(self):
        p = Provenance.create("d1", "v1")
        assert p.contract_id is None
        assert p.contract_satisfied is None
        assert p.contract_violations == []
        assert p.tokens_used is None
        assert p.cost_usd is None

    def test_provenance_with_usage(self):
        p = Provenance.create("d1", "v1", tokens_used=5000, cost_usd=0.03)
        assert p.tokens_used == 5000
        assert p.cost_usd == 0.03

    def test_provenance_backward_compat(self):
        old_data = {
            "produced_by": "d1", "model_version": "v1",
            "payload_mode_used": "text", "verified": False,
        }
        p = Provenance.model_validate(old_data)
        assert p.produced_by == "d1"
        assert p.contract_violations == []


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


class TestContractValidation:
    def test_no_violations(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(
            objective="test", success_criteria=[],
            deadline="2099-12-31T23:59:59+00:00",
        )
        p = Provenance.create("d1", "v1")
        violations = _validate_contract(contract, p)
        assert violations == []

    def test_deadline_exceeded(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(
            objective="test", success_criteria=[],
            deadline="2020-01-01T00:00:00+00:00",
        )
        p = Provenance.create("d1", "v1")
        violations = _validate_contract(contract, p)
        assert "deadline_exceeded" in violations

    def test_budget_tokens_exceeded(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(
            objective="test", success_criteria=[],
            policy=PolicyEnvelope(budget=BudgetPolicy(max_tokens=1000)),
        )
        p = Provenance.create("d1", "v1", tokens_used=2000)
        violations = _validate_contract(contract, p)
        assert "budget_tokens_exceeded" in violations

    def test_budget_cost_exceeded(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(
            objective="test", success_criteria=[],
            policy=PolicyEnvelope(budget=BudgetPolicy(max_cost_usd=0.01)),
        )
        p = Provenance.create("d1", "v1", cost_usd=0.05)
        violations = _validate_contract(contract, p)
        assert "budget_cost_exceeded" in violations

    def test_budget_skipped_when_no_usage(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(
            objective="test", success_criteria=[],
            policy=PolicyEnvelope(budget=BudgetPolicy(max_tokens=100)),
        )
        p = Provenance.create("d1", "v1")
        violations = _validate_contract(contract, p)
        assert violations == []

    def test_multiple_violations(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(
            objective="test", success_criteria=[],
            deadline="2020-01-01T00:00:00+00:00",
            policy=PolicyEnvelope(budget=BudgetPolicy(max_tokens=100)),
        )
        p = Provenance.create("d1", "v1", tokens_used=500)
        violations = _validate_contract(contract, p)
        assert "deadline_exceeded" in violations
        assert "budget_tokens_exceeded" in violations

    def test_no_budget_no_deadline_always_passes(self):
        from ldp_protocol.client import _validate_contract
        contract = DelegationContract(objective="draft", success_criteria=["be creative"])
        p = Provenance.create("d1", "v1")
        violations = _validate_contract(contract, p)
        assert violations == []


class TestSessionAdvanced:
    def test_session_expires_after_ttl(self):
        from datetime import datetime, timezone, timedelta
        from ldp_protocol.types.session import LdpSession, SessionState
        session = LdpSession(
            session_id="s1", remote_url="http://localhost",
            remote_delegate_id="remote", trust_domain=TrustDomain(name="test"),
            ttl_secs=1,
        )
        session.last_used = datetime.now(timezone.utc) - timedelta(seconds=2)
        assert not session.is_active

    def test_session_active_within_ttl(self):
        from ldp_protocol.types.session import LdpSession
        session = LdpSession(
            session_id="s1", remote_url="http://localhost",
            remote_delegate_id="remote", trust_domain=TrustDomain(name="test"),
            ttl_secs=3600,
        )
        assert session.is_active

    def test_closed_session_not_active(self):
        from ldp_protocol.types.session import LdpSession, SessionState
        session = LdpSession(
            session_id="s1", remote_url="http://localhost",
            remote_delegate_id="remote", state=SessionState.CLOSED,
            trust_domain=TrustDomain(name="test"),
        )
        assert not session.is_active

    def test_session_touch_updates_timestamp(self):
        import time
        from ldp_protocol.types.session import LdpSession
        session = LdpSession(
            session_id="s1", remote_url="http://localhost",
            remote_delegate_id="remote", trust_domain=TrustDomain(name="test"),
        )
        old_time = session.last_used
        time.sleep(0.01)
        session.touch()
        assert session.last_used >= old_time

    def test_session_config_defaults(self):
        config = SessionConfig()
        assert config.ttl_secs == 3600
        assert PayloadMode.SEMANTIC_FRAME in config.preferred_payload_modes
        assert config.required_trust_domain is None


class TestMessagesAdvanced:
    def test_all_message_factory_methods(self):
        types_list = [
            LdpMessageBody.hello("id", [PayloadMode.TEXT]),
            LdpMessageBody.capability_manifest({"caps": []}),
            LdpMessageBody.session_propose({"ttl": 3600}),
            LdpMessageBody.session_accept("s1", PayloadMode.TEXT),
            LdpMessageBody.session_reject("no"),
            LdpMessageBody.task_submit("t1", "echo", {"data": 1}),
            LdpMessageBody.task_update("t1", progress=0.5, message="working"),
            LdpMessageBody.task_result("t1", {"out": 1}, Provenance.create("d1", "v1")),
            LdpMessageBody.task_failed("t1", "error"),
            LdpMessageBody.task_cancel("t1"),
            LdpMessageBody.session_close("done"),
        ]
        for body in types_list:
            assert body.type is not None
            data = body.model_dump()
            restored = LdpMessageBody.model_validate(data)
            assert restored.type == body.type

    def test_envelope_with_signature_fields(self):
        body = LdpMessageBody.hello("test", [PayloadMode.TEXT])
        env = LdpEnvelope.create("s1", "a", "b", body)
        assert env.signature is None
        assert env.signature_algorithm is None
        env.signature = "abc123"
        env.signature_algorithm = "hmac-sha256"
        data = env.model_dump(by_alias=True)
        assert data["signature"] == "abc123"
