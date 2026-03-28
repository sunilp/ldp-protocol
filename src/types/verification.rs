//! LDP verification and lineage types.

use serde::{Deserialize, Serialize};

/// How a result was verified.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerificationStatus {
    #[default]
    Unverified,
    SelfVerified,
    PeerVerified,
    ToolVerified,
    HumanVerified,
}

/// Reference to supporting evidence.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvidenceRef {
    pub source: String,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub uri: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub summary: Option<String>,
}

/// One hop in a delegation lineage chain.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProvenanceEntry {
    pub delegate_id: String,
    pub model_version: String,
    pub step: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<String>,
    #[serde(default)]
    pub verification_status: VerificationStatus,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_verification_is_unverified() {
        assert_eq!(
            VerificationStatus::default(),
            VerificationStatus::Unverified
        );
    }

    #[test]
    fn verification_status_serialization() {
        let status = VerificationStatus::SelfVerified;
        let json = serde_json::to_value(&status).unwrap();
        assert_eq!(json, "self_verified");
        let restored: VerificationStatus = serde_json::from_value(json).unwrap();
        assert_eq!(restored, VerificationStatus::SelfVerified);
    }

    #[test]
    fn all_verification_variants_serialize() {
        for (variant, expected) in [
            (VerificationStatus::Unverified, "unverified"),
            (VerificationStatus::SelfVerified, "self_verified"),
            (VerificationStatus::PeerVerified, "peer_verified"),
            (VerificationStatus::ToolVerified, "tool_verified"),
            (VerificationStatus::HumanVerified, "human_verified"),
        ] {
            let json = serde_json::to_value(&variant).unwrap();
            assert_eq!(json, expected);
        }
    }

    #[test]
    fn evidence_ref_creation() {
        let evidence = EvidenceRef {
            source: "pytest".into(),
            kind: "test_results".into(),
            uri: Some("https://ci.example.com/run/123".into()),
            summary: Some("All 50 tests passed".into()),
        };
        let json = serde_json::to_value(&evidence).unwrap();
        let restored: EvidenceRef = serde_json::from_value(json).unwrap();
        assert_eq!(restored.source, "pytest");
        assert_eq!(restored.kind, "test_results");
    }

    #[test]
    fn provenance_entry_creation() {
        let entry = ProvenanceEntry {
            delegate_id: "ldp:delegate:alpha".into(),
            model_version: "v1.0".into(),
            step: "reasoning".into(),
            timestamp: Some("2026-03-15T12:00:00Z".into()),
            verification_status: VerificationStatus::SelfVerified,
        };
        let json = serde_json::to_value(&entry).unwrap();
        let restored: ProvenanceEntry = serde_json::from_value(json).unwrap();
        assert_eq!(restored.delegate_id, "ldp:delegate:alpha");
        assert_eq!(
            restored.verification_status,
            VerificationStatus::SelfVerified
        );
    }
}
