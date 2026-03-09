//! JamJet plugin registration for LDP.
//!
//! This module provides the glue code to register the LDP adapter with
//! JamJet's `ProtocolRegistry` — **without modifying any JamJet source code**.
//!
//! # Plugin Architecture
//!
//! JamJet's `ProtocolRegistry` is designed for runtime extension:
//!
//! ```text
//! ┌─────────────────────────────────────┐
//! │  JamJet Runtime (unmodified)        │
//! │                                     │
//! │  ProtocolRegistry                   │
//! │  ├── "mcp"  → McpAdapter  (built-in)│
//! │  ├── "a2a"  → A2aAdapter  (built-in)│
//! │  ├── "anp"  → AnpAdapter  (built-in)│
//! │  └── "ldp"  → LdpAdapter  (plugin!) │  ← registered at startup
//! │                                     │
//! └─────────────────────────────────────┘
//! ```
//!
//! No new `NodeKind` variant needed. LDP tasks are dispatched via
//! URL-based routing: any URL with `ldp://` prefix is automatically
//! routed to the LDP adapter by `ProtocolRegistry::adapter_for_url()`.
//!
//! # Usage
//!
//! ```rust,ignore
//! use jamjet_ldp::plugin::register_ldp;
//! use jamjet_protocols::ProtocolRegistry;
//!
//! let mut registry = ProtocolRegistry::new();
//! // ... register built-in adapters ...
//! register_ldp(&mut registry, None); // default config
//! ```

use crate::config::LdpAdapterConfig;
use crate::LdpAdapter;
use jamjet_protocols::ProtocolRegistry;
use std::sync::Arc;

/// Register the LDP adapter with a JamJet `ProtocolRegistry`.
///
/// This is the single integration point. Call this at startup alongside
/// the built-in adapter registrations. No JamJet source changes required.
///
/// # Arguments
///
/// * `registry` — The JamJet protocol registry to register with.
/// * `config` — Optional LDP configuration. Uses defaults if `None`.
///
/// # URL Routing
///
/// Registers `"ldp://"` as the URL prefix. Any remote agent URL starting
/// with `ldp://` will be automatically routed to this adapter.
pub fn register_ldp(registry: &mut ProtocolRegistry, config: Option<LdpAdapterConfig>) {
    let config = config.unwrap_or_default();
    let adapter = Arc::new(LdpAdapter::new(config));
    registry.register("ldp", adapter, vec!["ldp://"]);
}

/// Create a standalone LDP adapter (for use outside JamJet's registry).
///
/// Useful for experiments and benchmarks that bypass the workflow engine.
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
}
