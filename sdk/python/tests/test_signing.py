"""Tests for LDP message signing."""

from ldp_protocol.signing import sign_envelope, verify_envelope, apply_signature
from ldp_protocol.types.messages import LdpEnvelope, LdpMessageBody
from ldp_protocol.types.payload import PayloadMode


class TestSigning:
    def _make_envelope(self) -> LdpEnvelope:
        return LdpEnvelope.create(
            session_id="session-1",
            from_id="from-delegate",
            to_id="to-delegate",
            body=LdpMessageBody.hello("test", [PayloadMode.TEXT]),
        )

    def test_sign_and_verify(self):
        env = self._make_envelope()
        sig = sign_envelope(env, "test-secret")
        assert sig
        assert verify_envelope(env, "test-secret", sig)

    def test_tampered_fails(self):
        env = self._make_envelope()
        sig = sign_envelope(env, "test-secret")
        env.to = "attacker"
        assert not verify_envelope(env, "test-secret", sig)

    def test_wrong_secret_fails(self):
        env = self._make_envelope()
        sig = sign_envelope(env, "secret-a")
        assert not verify_envelope(env, "secret-b", sig)

    def test_apply_signature(self):
        env = self._make_envelope()
        apply_signature(env, "test-secret")
        assert env.signature is not None
        assert env.signature_algorithm == "hmac-sha256"

    def test_task_submit_signing(self):
        env = LdpEnvelope.create(
            session_id="s1",
            from_id="from",
            to_id="to",
            body=LdpMessageBody.task_submit("t1", "echo", {"data": 1}),
        )
        sig = sign_envelope(env, "secret")
        assert verify_envelope(env, "secret", sig)
