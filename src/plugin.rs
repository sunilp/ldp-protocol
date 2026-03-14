//! LDP plugin registration.
//!
//! Provides registration for the LDP adapter with a `ProtocolRegistry`.
//!
//! # Standalone Usage
//!
//! ```rust,ignore
//! use ldp_protocol::plugin::register_ldp;
//! use ldp_protocol::protocol::ProtocolRegistry;
//!
//! let mut registry = ProtocolRegistry::new();
//! register_ldp(&mut registry, None);
//! ```
//!
//! # JamJet Usage (with `jamjet` feature)
//!
//! ```rust,ignore
//! use ldp_protocol::plugin::register_ldp_jamjet;
//! use jamjet_protocols::ProtocolRegistry;
//!
//! let mut registry = ProtocolRegistry::new();
//! register_ldp_jamjet(&mut registry, None);
//! ```

use crate::config::LdpAdapterConfig;
use crate::protocol::ProtocolRegistry;
use crate::LdpAdapter;
use std::sync::Arc;

/// Register the LDP adapter with a `ProtocolRegistry`.
///
/// # Arguments
///
/// * `registry` — The protocol registry to register with.
/// * `config` — Optional LDP configuration. Uses defaults if `None`.
///
/// # URL Routing
///
/// Registers `"ldp://"` as the URL prefix. Any URL starting with `ldp://`
/// will be routed to the LDP adapter.
pub fn register_ldp(registry: &mut ProtocolRegistry, config: Option<LdpAdapterConfig>) {
    let config = config.unwrap_or_default();
    let adapter = Arc::new(LdpAdapter::new(config));
    registry.register("ldp", adapter, vec!["ldp://"]);
}

/// Register the LDP adapter with JamJet's `ProtocolRegistry`.
///
/// This bridges LDP into JamJet's runtime without modifying JamJet source code.
/// Only available when the `jamjet` feature is enabled.
#[cfg(feature = "jamjet")]
pub fn register_ldp_jamjet(
    registry: &mut jamjet_protocols::ProtocolRegistry,
    config: Option<LdpAdapterConfig>,
) {
    let config = config.unwrap_or_default();
    let adapter = Arc::new(LdpAdapter::new(config));
    registry.register("ldp", adapter, vec!["ldp://"]);
}

/// Create a standalone LDP adapter instance.
///
/// Useful for direct usage without a registry.
pub fn create_adapter(config: Option<LdpAdapterConfig>) -> Arc<LdpAdapter> {
    Arc::new(LdpAdapter::new(config.unwrap_or_default()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn register_ldp_in_registry() {
        let mut registry = ProtocolRegistry::new();
        register_ldp(&mut registry, None);

        assert!(registry.adapter("ldp").is_some());
        assert!(registry.protocols().contains(&"ldp"));
    }

    #[test]
    fn url_routing_matches_ldp_prefix() {
        let mut registry = ProtocolRegistry::new();
        register_ldp(&mut registry, None);

        assert!(registry.adapter_for_url("ldp://delegate.example.com").is_some());
        assert!(registry.adapter_for_url("https://not-ldp.com").is_none());
    }

    #[tokio::test]
    async fn create_standalone_adapter() {
        let adapter = create_adapter(None);
        assert_eq!(adapter.session_manager().active_count().await, 0);
    }
}
