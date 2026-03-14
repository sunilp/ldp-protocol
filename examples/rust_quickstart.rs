//! LDP Quick Start — register LDP in a JamJet runtime and invoke a delegate.
//!
//! This example shows how to:
//! 1. Register LDP as a protocol adapter alongside MCP and A2A
//! 2. Discover a remote delegate's identity and capabilities
//! 3. Invoke a task via the LDP session lifecycle
//! 4. Inspect provenance in the result
//!
//! Usage:
//!     cargo run --example rust_quickstart
//!
//! Requires a running LDP delegate at localhost:8090 (see examples/python_sdk/ldp_delegate.py)

use ldp_protocol::{register_ldp, LdpAdapterConfig, SessionConfig, PayloadMode};

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

    // 2. In a real JamJet setup, register with the protocol registry:
    //
    //    let mut registry = default_protocol_registry(); // MCP, A2A built-in
    //    register_ldp(&mut registry, Some(config));      // LDP plugged in
    //
    //    // Now ldp:// URLs are handled by LDP, a2a:// by A2A, mcp:// by MCP
    //    let caps = registry.discover("ldp://localhost:8090").await?;
    //    let handle = registry.invoke("ldp://localhost:8090", task).await?;

    println!("\nLDP adapter ready. In production, register with:");
    println!("  register_ldp(&mut registry, Some(config));");
    println!("\nThen use ldp:// URLs in workflow nodes:");
    println!("  registry.discover(\"ldp://localhost:8090\")");
    println!("  registry.invoke(\"ldp://localhost:8090\", task)");
    println!("\n=== Done ===");
}
