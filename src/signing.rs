//! HMAC message signing and verification for LDP envelopes.

use crate::types::messages::{LdpEnvelope, LdpMessageBody};
use hmac::{Hmac, Mac};
use sha2::Sha256;
use subtle::ConstantTimeEq;

type HmacSha256 = Hmac<Sha256>;

/// Sign an envelope and return the hex-encoded HMAC-SHA256 signature.
///
/// Uses a canonical field order (not JSON serialization) to ensure
/// cross-SDK compatibility between Rust and Python.
pub fn sign_envelope(envelope: &LdpEnvelope, secret: &str) -> String {
    let mut mac =
        HmacSha256::new_from_slice(secret.as_bytes()).expect("HMAC accepts any key length");

    // Canonical signing input: fixed field order, "|" separator
    mac.update(envelope.from.as_bytes());
    mac.update(b"|");
    mac.update(envelope.to.as_bytes());
    mac.update(b"|");
    mac.update(envelope.session_id.as_bytes());
    mac.update(b"|");
    mac.update(envelope.timestamp.as_bytes());
    mac.update(b"|");
    mac.update(envelope.message_id.as_bytes());
    mac.update(b"|");

    // Sign body type and key identifying fields
    let body_type = match &envelope.body {
        LdpMessageBody::Hello { delegate_id, .. } => {
            mac.update(delegate_id.as_bytes());
            "HELLO"
        }
        LdpMessageBody::CapabilityManifest { .. } => "CAPABILITY_MANIFEST",
        LdpMessageBody::SessionPropose { .. } => "SESSION_PROPOSE",
        LdpMessageBody::SessionAccept { session_id, .. } => {
            mac.update(session_id.as_bytes());
            "SESSION_ACCEPT"
        }
        LdpMessageBody::SessionReject { reason, .. } => {
            mac.update(reason.as_bytes());
            "SESSION_REJECT"
        }
        LdpMessageBody::TaskSubmit {
            task_id, skill, ..
        } => {
            mac.update(task_id.as_bytes());
            mac.update(b"|");
            mac.update(skill.as_bytes());
            "TASK_SUBMIT"
        }
        LdpMessageBody::TaskUpdate { task_id, .. } => {
            mac.update(task_id.as_bytes());
            "TASK_UPDATE"
        }
        LdpMessageBody::TaskResult { task_id, .. } => {
            mac.update(task_id.as_bytes());
            "TASK_RESULT"
        }
        LdpMessageBody::TaskFailed { task_id, .. } => {
            mac.update(task_id.as_bytes());
            "TASK_FAILED"
        }
        LdpMessageBody::TaskCancel { task_id } => {
            mac.update(task_id.as_bytes());
            "TASK_CANCEL"
        }
        LdpMessageBody::Attestation { .. } => "ATTESTATION",
        LdpMessageBody::SessionClose { .. } => "SESSION_CLOSE",
    };
    mac.update(b"|");
    mac.update(body_type.as_bytes());

    hex::encode(mac.finalize().into_bytes())
}

/// Verify an envelope's signature using constant-time comparison.
pub fn verify_envelope(envelope: &LdpEnvelope, secret: &str, signature: &str) -> bool {
    let expected = sign_envelope(envelope, secret);
    let expected_bytes = expected.as_bytes();
    let signature_bytes = signature.as_bytes();
    if expected_bytes.len() != signature_bytes.len() {
        return false;
    }
    expected_bytes.ct_eq(signature_bytes).into()
}

/// Apply a signature to an envelope (mutates in place).
pub fn apply_signature(envelope: &mut LdpEnvelope, secret: &str) {
    let sig = sign_envelope(envelope, secret);
    envelope.signature = Some(sig);
    envelope.signature_algorithm = Some("hmac-sha256".into());
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::payload::PayloadMode;

    fn make_envelope() -> LdpEnvelope {
        LdpEnvelope::new(
            "session-1",
            "from-delegate",
            "to-delegate",
            LdpMessageBody::Hello {
                delegate_id: "test".into(),
                supported_modes: vec![PayloadMode::Text],
            },
            PayloadMode::Text,
        )
    }

    #[test]
    fn sign_and_verify_roundtrip() {
        let envelope = make_envelope();
        let sig = sign_envelope(&envelope, "test-secret");
        assert!(!sig.is_empty());
        assert!(verify_envelope(&envelope, "test-secret", &sig));
    }

    #[test]
    fn tampered_message_fails() {
        let envelope = make_envelope();
        let sig = sign_envelope(&envelope, "test-secret");
        let mut tampered = envelope.clone();
        tampered.from = "attacker".into();
        assert!(!verify_envelope(&tampered, "test-secret", &sig));
    }

    #[test]
    fn wrong_secret_fails() {
        let envelope = make_envelope();
        let sig = sign_envelope(&envelope, "secret-a");
        assert!(!verify_envelope(&envelope, "secret-b", &sig));
    }

    #[test]
    fn apply_signature_sets_fields() {
        let mut envelope = make_envelope();
        apply_signature(&mut envelope, "test-secret");
        assert!(envelope.signature.is_some());
        assert_eq!(
            envelope.signature_algorithm.as_deref(),
            Some("hmac-sha256")
        );
    }

    #[test]
    fn task_submit_signing() {
        let envelope = LdpEnvelope::new(
            "s1",
            "from",
            "to",
            LdpMessageBody::TaskSubmit {
                task_id: "t1".into(),
                skill: "echo".into(),
                input: serde_json::json!({"data": 1}),
            },
            PayloadMode::Text,
        );
        let sig = sign_envelope(&envelope, "secret");
        assert!(verify_envelope(&envelope, "secret", &sig));
    }
}
