//! LDP provenance tracking.
//!
//! Every LDP task result carries provenance metadata: who produced it,
//! which model, what payload mode, confidence, and verification status.

use crate::types::payload::PayloadMode;
use crate::types::verification::{VerificationStatus, EvidenceRef, ProvenanceEntry};
use serde::{Deserialize, Serialize};

/// Provenance metadata attached to every LDP task result.
///
/// Embedded in the output `Value` so it flows through JamJet's existing
/// pipeline without modification.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Provenance {
    /// Delegate ID that produced this result.
    pub produced_by: String,

    /// Model version used.
    pub model_version: String,

    /// Payload mode used for this exchange.
    pub payload_mode_used: PayloadMode,

    /// Self-reported confidence (0.0 – 1.0).
    pub confidence: Option<f64>,

    /// Whether the result has been verified (e.g. by a second delegate).
    #[deprecated(note = "Use verification_status instead")]
    #[serde(default)]
    pub verified: bool,

    /// Session ID in which this result was produced.
    pub session_id: Option<String>,

    /// Timestamp of production.
    pub timestamp: Option<String>,

    /// Tokens consumed by the delegate (delegate-reported).
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub tokens_used: Option<u64>,

    /// Cost incurred in USD (delegate-reported).
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub cost_usd: Option<f64>,

    /// Contract ID this result was produced under.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub contract_id: Option<String>,

    /// Whether the contract was satisfied (set by client-side validation).
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub contract_satisfied: Option<bool>,

    /// List of contract violation codes (set by client-side validation).
    #[serde(default)]
    pub contract_violations: Vec<String>,

    /// Granular verification status.
    #[serde(default)]
    pub verification_status: VerificationStatus,

    /// Supporting evidence references.
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,

    /// Delegation lineage chain (newest hop first).
    #[serde(default)]
    pub lineage: Vec<ProvenanceEntry>,
}

impl Provenance {
    /// Create a new provenance record.
    #[allow(deprecated)]
    pub fn new(delegate_id: impl Into<String>, model_version: impl Into<String>) -> Self {
        Self {
            produced_by: delegate_id.into(),
            model_version: model_version.into(),
            payload_mode_used: PayloadMode::SemanticFrame,
            confidence: None,
            verified: false,
            session_id: None,
            timestamp: Some(chrono::Utc::now().to_rfc3339()),
            tokens_used: None,
            cost_usd: None,
            contract_id: None,
            contract_satisfied: None,
            contract_violations: Vec::new(),
            verification_status: VerificationStatus::Unverified,
            evidence: Vec::new(),
            lineage: Vec::new(),
        }
    }

    /// Sync verified bool with verification_status.
    /// verification_status is authoritative.
    pub fn normalize(&mut self) {
        #[allow(deprecated)]
        {
            if self.verification_status == VerificationStatus::Unverified && self.verified {
                self.verification_status = VerificationStatus::SelfVerified;
            }
            self.verified = self.verification_status != VerificationStatus::Unverified;
        }
    }

    /// Convert to a JSON Value for embedding in task output.
    pub fn to_value(&self) -> serde_json::Value {
        serde_json::to_value(self).unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_has_no_contract_fields() {
        let p = Provenance::new("d1", "v1");
        assert!(p.contract_id.is_none());
        assert!(p.contract_satisfied.is_none());
        assert!(p.contract_violations.is_empty());
        assert!(p.tokens_used.is_none());
        assert!(p.cost_usd.is_none());
    }

    #[test]
    fn with_usage() {
        let mut p = Provenance::new("d1", "v1");
        p.tokens_used = Some(5000);
        p.cost_usd = Some(0.03);
        let json = serde_json::to_value(&p).unwrap();
        let restored: Provenance = serde_json::from_value(json).unwrap();
        assert_eq!(restored.tokens_used, Some(5000));
        assert_eq!(restored.cost_usd, Some(0.03));
    }

    #[test]
    fn backward_compat_deserialization() {
        let old_json = serde_json::json!({
            "produced_by": "d1",
            "model_version": "v1",
            "payload_mode_used": "text",
            "verified": false
        });
        let p: Provenance = serde_json::from_value(old_json).unwrap();
        assert_eq!(p.produced_by, "d1");
        assert!(p.contract_id.is_none());
        assert!(p.contract_violations.is_empty());
    }

    #[test]
    fn provenance_new_has_unverified_status() {
        let p = Provenance::new("d1", "v1");
        assert_eq!(p.verification_status, VerificationStatus::Unverified);
        assert!(p.evidence.is_empty());
        assert!(p.lineage.is_empty());
    }

    #[test]
    fn provenance_normalize_syncs_verified_to_status() {
        let mut p = Provenance::new("d1", "v1");
        p.verification_status = VerificationStatus::PeerVerified;
        p.normalize();
        #[allow(deprecated)]
        {
            assert!(p.verified);
        }
    }

    #[test]
    fn provenance_normalize_syncs_old_verified_true() {
        let mut p = Provenance::new("d1", "v1");
        #[allow(deprecated)]
        {
            p.verified = true;
        }
        p.normalize();
        assert_eq!(p.verification_status, VerificationStatus::SelfVerified);
    }

    #[test]
    fn provenance_backward_compat_no_verification_fields() {
        let old_json = serde_json::json!({
            "produced_by": "d1",
            "model_version": "v1",
            "payload_mode_used": "text",
            "verified": true
        });
        let mut p: Provenance = serde_json::from_value(old_json).unwrap();
        p.normalize();
        assert_eq!(p.verification_status, VerificationStatus::SelfVerified);
        assert!(p.evidence.is_empty());
        assert!(p.lineage.is_empty());
    }
}
