//! LDP adapter configuration.

use crate::types::session::SessionConfig;
use serde::{Deserialize, Serialize};

/// Configuration for the LDP protocol adapter.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpAdapterConfig {
    /// This adapter's delegate ID.
    pub delegate_id: String,

    /// Session configuration defaults.
    #[serde(default)]
    pub session: SessionConfig,

    /// Whether to enforce trust domain checks.
    #[serde(default = "default_true")]
    pub enforce_trust_domains: bool,

    /// Whether to attach provenance to all task results.
    #[serde(default = "default_true")]
    pub attach_provenance: bool,
}

fn default_true() -> bool {
    true
}

impl Default for LdpAdapterConfig {
    fn default() -> Self {
        Self {
            delegate_id: "ldp:delegate:local".into(),
            session: SessionConfig::default(),
            enforce_trust_domains: true,
            attach_provenance: true,
        }
    }
}
