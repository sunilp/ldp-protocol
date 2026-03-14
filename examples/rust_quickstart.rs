//! LDP Quick Start — create an LDP adapter and invoke a delegate.
//!
//! This example shows how to:
//! 1. Create an LDP adapter (standalone or with a registry)
//! 2. Discover a remote delegate's identity and capabilities
//! 3. Invoke a task via the LDP session lifecycle
//! 4. Inspect provenance in the result
//!
//! Usage:
//!     cargo run --example rust_quickstart
//!
//! Requires a running LDP delegate at localhost:8090 (see examples/python_sdk/ldp_delegate.py)

use ldp_protocol::{register_ldp, LdpAdapterConfig, SessionConfig, PayloadMode};
use ldp_protocol::protocol::ProtocolRegistry;

#[tokio::main]
async fn main() {
    println!("=== LDP Quick Start ===\n");

    // 1. Create LDP adapter with custom config
    let config = LdpAdapterConfig {
        delegate_id: "ldp:delegate:my-orchestrator".into(),
        session: SessionConfig {
            preferred_payload_modes: vec![PayloadMode::SemanticFrame, PayloadMode::Text],
            ttl_secs: 3600,
            required_trust_domain: None,
        },
        enforce_trust_domains: false,
        attach_provenance: true,
    };

    println!("Config: delegate_id={}", config.delegate_id);
    println!("  payload modes: {:?}", config.session.preferred_payload_modes);
    println!("  trust enforcement: {}", config.enforce_trust_domains);
    println!("  attach provenance: {}", config.attach_provenance);

    // 2. Register with a protocol registry
    let mut registry = ProtocolRegistry::new();
    register_ldp(&mut registry, Some(config));

    // Now ldp:// URLs are handled by the LDP adapter
    println!("\nRegistered protocols: {:?}", registry.protocols());
    println!("  ldp:// adapter: {}", registry.adapter_for_url("ldp://localhost:8090").is_some());

    // 3. In production, use the registry to discover and invoke:
    //
    //    let caps = registry.adapter_for_url("ldp://localhost:8090")
    //        .unwrap()
    //        .discover("http://localhost:8090").await?;
    //
    //    let handle = registry.adapter_for_url("ldp://localhost:8090")
    //        .unwrap()
    //        .invoke("http://localhost:8090", task).await?;

    println!("\nUse the adapter via the registry:");
    println!("  registry.adapter_for_url(\"ldp://...\").unwrap().discover(url).await");
    println!("  registry.adapter_for_url(\"ldp://...\").unwrap().invoke(url, task).await");
    println!("\n=== Done ===");
}
