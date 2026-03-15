//! LDP adapter configuration.

use crate::types::session::SessionConfig;
use crate::types::trust::TrustDomain;
use serde::{Deserialize, Serialize};

/// Configuration for the LDP protocol adapter.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpAdapterConfig {
    /// This adapter's delegate ID.
    pub delegate_id: String,

    /// Trust domain for this adapter.
    #[serde(default)]
    pub trust_domain: TrustDomain,

    /// Session configuration defaults.
    #[serde(default)]
    pub session: SessionConfig,

    /// Whether to enforce trust domain checks.
    #[serde(default = "default_true")]
    pub enforce_trust_domains: bool,

    /// Whether to attach provenance to all task results.
    #[serde(default = "default_true")]
    pub attach_provenance: bool,

    /// Shared secret for HMAC message signing. If None, signing is disabled.
    #[serde(default)]
    pub signing_secret: Option<String>,
}

fn default_true() -> bool {
    true
}

impl Default for LdpAdapterConfig {
    fn default() -> Self {
        Self {
            delegate_id: "ldp:delegate:local".into(),
            trust_domain: TrustDomain::new("default"),
            session: SessionConfig::default(),
            enforce_trust_domains: true,
            attach_provenance: true,
            signing_secret: None,
        }
    }
}
