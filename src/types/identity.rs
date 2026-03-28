//! LDP delegate identity card.
//!
//! Extends JamJet's `AgentCard` with AI-native identity fields:
//! model family, weights fingerprint, reasoning profile, trust domain, etc.

use crate::types::capability::LdpCapability;
use crate::types::payload::PayloadMode;
use crate::types::trust::TrustDomain;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Full LDP identity card for a delegate.
///
/// This is the rich typed representation maintained internally by the adapter.
/// A subset of these fields is also written into `AgentCard.labels` with
/// `ldp.*` keys for interoperability with JamJet's existing infrastructure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpIdentityCard {
    /// Unique delegate identifier (e.g. "ldp:delegate:challenger-alpha").
    pub delegate_id: String,

    /// Human-readable name.
    pub name: String,

    /// Optional description of the delegate's purpose.
    pub description: Option<String>,

    /// Model family (e.g. "Claude", "GPT", "Gemini").
    pub model_family: String,

    /// Model version (e.g. "2026.03").
    pub model_version: String,

    /// SHA-256 fingerprint of model weights, if available.
    pub weights_fingerprint: Option<String>,

    /// Trust domain this delegate belongs to.
    pub trust_domain: TrustDomain,

    /// Context window size in tokens.
    pub context_window: u64,

    /// Reasoning profile (e.g. "analytical", "creative", "adversarial-analytical").
    pub reasoning_profile: Option<String>,

    /// Cost profile (e.g. "low", "medium", "high").
    pub cost_profile: Option<String>,

    /// Latency profile (e.g. "p50:2000ms", "p99:8000ms").
    pub latency_profile: Option<String>,

    /// Jurisdictional constraints (e.g. "us-east", "eu-west").
    pub jurisdiction: Option<String>,

    /// Capabilities this delegate offers.
    pub capabilities: Vec<LdpCapability>,

    /// Supported payload modes, ordered by preference.
    pub supported_payload_modes: Vec<PayloadMode>,

    /// Endpoint URL for the delegate.
    pub endpoint: String,

    /// Additional metadata.
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl LdpIdentityCard {
    /// Convert identity fields into `AgentCard.labels` entries.
    ///
    /// Keys are prefixed with `ldp.` to avoid collisions with other protocols.
    pub fn to_labels(&self) -> HashMap<String, String> {
        let mut labels = HashMap::new();
        labels.insert("ldp.delegate_id".into(), self.delegate_id.clone());
        labels.insert("ldp.model_family".into(), self.model_family.clone());
        labels.insert("ldp.model_version".into(), self.model_version.clone());
        labels.insert("ldp.trust_domain".into(), self.trust_domain.name.clone());
        labels.insert("ldp.context_window".into(), self.context_window.to_string());

        if let Some(ref fp) = self.weights_fingerprint {
            labels.insert("ldp.weights_fingerprint".into(), fp.clone());
        }
        if let Some(ref rp) = self.reasoning_profile {
            labels.insert("ldp.reasoning_profile".into(), rp.clone());
        }
        if let Some(ref cp) = self.cost_profile {
            labels.insert("ldp.cost_profile".into(), cp.clone());
        }
        if let Some(ref lp) = self.latency_profile {
            labels.insert("ldp.latency_profile".into(), lp.clone());
        }
        if let Some(ref j) = self.jurisdiction {
            labels.insert("ldp.jurisdiction".into(), j.clone());
        }

        // Payload modes as comma-separated list.
        let modes: Vec<String> = self
            .supported_payload_modes
            .iter()
            .map(|m| m.to_string())
            .collect();
        labels.insert("ldp.payload_modes".into(), modes.join(","));

        labels
    }
}
