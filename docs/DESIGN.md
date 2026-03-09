# LDP Adapter Design for JamJet

## Integration Pattern: External Plugin (Zero JamJet Changes)

LDP integrates with JamJet as an **external plugin** — no JamJet source modifications required.

JamJet's `ProtocolRegistry` is already designed for runtime extension. LDP registers itself at startup via a single function call:

```rust
use jamjet_ldp::register_ldp;

let mut registry = default_protocol_registry(); // MCP, A2A, ANP built-in
register_ldp(&mut registry, None);              // LDP plugged in
```

### Why Plugin, Not Baked-In

| Concern | Baked-In | Plugin |
|---------|----------|--------|
| JamJet CI | Breaks without ldp-research | No impact |
| JamJet repo | Must include LDP code or path dep | Clean |
| LDP repo (private) | Coupled to JamJet releases | Independent |
| Deployment | Always loaded | Opt-in |
| New NodeKind? | Yes (LdpTask variant) | No — URL routing via `adapter_for_url("ldp://...")` |

### How URL-Based Dispatch Works

```
Workflow references remote_agent: "ldp://delegate.example.com/reasoner"
  → ProtocolRegistry.adapter_for_url("ldp://...") matches "ldp://" prefix
  → Routes to LdpAdapter
  → LdpAdapter.invoke() handles session + task transparently
```

No new `NodeKind` variant needed. Existing `A2aTask` or generic protocol dispatch handles LDP URLs. The registry's longest-prefix-match does the routing.

## JamJet Integration Points

Based on analysis of JamJet's protocol adapter architecture (MCP + A2A patterns).

### What We Implement

| Component | JamJet Pattern | LDP Implementation |
|---|---|---|
| `ProtocolAdapter` trait | 7 methods: discover, invoke, stream, stream_structured, stream_with_backpressure, status, cancel | `LdpAdapter` struct |
| Agent identity | `AgentCard` with labels map | Extend via `labels` with `ldp.*` keys + dedicated `LdpIdentityCard` |
| Discovery | `adapter.discover(url)` → `RemoteCapabilities` | Fetch LDP identity card + capability manifest, map to `RemoteCapabilities` |
| Task submission | `adapter.invoke(url, task)` → `TaskHandle` | Create LDP session (if needed) → TASK_SUBMIT → return handle |
| Streaming | `adapter.stream(url, task)` → `TaskStream` | Subscribe to TASK_UPDATE events from session |
| Status | `adapter.status(url, task_id)` → `TaskStatus` | Map LDP task lifecycle to JamJet TaskStatus |
| Registration | `ProtocolRegistry.register("ldp", adapter, prefixes)` | Register with "ldp" name and "ldp://" prefix |

### Key Difference from MCP/A2A: Sessions

MCP and A2A are stateless per-invocation. LDP has **sessions** (governed multi-round contexts).

Design decision: **session management lives inside the adapter**. From JamJet's perspective, `invoke()` is still request→response. Internally, the LDP adapter:

1. Checks if a session exists for this (url, session_config) pair
2. If not, runs HELLO → CAPABILITY_MANIFEST → SESSION_PROPOSE → SESSION_ACCEPT
3. Caches the session
4. Sends TASK_SUBMIT within the session
5. Returns TaskHandle

This keeps the JamJet integration clean -- LDP sessions are transparent to the workflow engine.

### AgentCard Extension Strategy

JamJet's `AgentCard` has a `labels: HashMap<String, String>` field. LDP identity fields go here:

```rust
// Standard AgentCard fields
card.id = "ldp:delegate:challenger-alpha"
card.name = "Challenger Alpha"
card.capabilities.protocols = vec!["ldp"]

// LDP extensions via labels
card.labels.insert("ldp.model_family", "AcmeLM")
card.labels.insert("ldp.model_version", "2026.03")
card.labels.insert("ldp.weights_fingerprint", "sha256:abc...")
card.labels.insert("ldp.trust_domain", "acme-prod")
card.labels.insert("ldp.context_window", "262144")
card.labels.insert("ldp.reasoning_profile", "adversarial-analytical")
card.labels.insert("ldp.cost_profile", "medium")
card.labels.insert("ldp.latency_profile", "p50:3000ms")
card.labels.insert("ldp.jurisdiction", "us-east")
```

Additionally, a full `LdpIdentityCard` struct is maintained internally for rich typed access.

### Payload Mode Negotiation

Payload mode negotiation happens during session establishment and is cached per-session:

```
Session {
    session_id,
    negotiated_mode: PayloadMode,  // The agreed-upon mode
    fallback_chain: [Mode1, Mode0], // Fallback sequence
    trust_domain: String,
    ...
}
```

For the MVP, only Mode 0 (Text) and Mode 1 (Semantic Frames / JSON) are implemented. Mode 1 maps directly to JamJet's existing JSON `Value` payloads.

### Provenance Tracking

Every `TaskStatus::Completed` from LDP carries provenance:

```rust
TaskStatus::Completed {
    output: json!({
        "result": ...,
        "ldp_provenance": {
            "produced_by": "ldp:delegate:reasonerB",
            "model_version": "2026.03",
            "payload_mode_used": "semantic_frame",
            "confidence": 0.84,
            "verified": true
        }
    })
}
```

The provenance is embedded in the output Value so it flows through JamJet's existing pipeline without modification.

### Trust Domain Enforcement

Before session establishment, the adapter validates trust domain compatibility:

```rust
async fn discover(&self, url: &str) -> Result<RemoteCapabilities, String> {
    let identity = self.fetch_identity_card(url).await?;

    // Trust domain check
    if let Some(required_domain) = &self.config.required_trust_domain {
        if identity.trust_domain != *required_domain {
            return Err(format!(
                "trust domain mismatch: expected {}, got {}",
                required_domain, identity.trust_domain
            ));
        }
    }

    // Convert to RemoteCapabilities
    ...
}
```

## File Structure

```
ldp-research/src/
├── lib.rs              # Public API
├── adapter.rs          # ProtocolAdapter implementation
├── plugin.rs           # JamJet plugin registration (register_ldp)
├── client.rs           # LDP HTTP client (sends LDP messages)
├── server.rs           # LDP server (receives LDP messages, serves identity)
├── types/
│   ├── mod.rs
│   ├── identity.rs     # LdpIdentityCard, DCI extensions
│   ├── capability.rs   # LdpCapability with quality/latency/cost
│   ├── session.rs      # Session state, negotiation
│   ├── messages.rs     # LDP message envelope, body types
│   ├── payload.rs      # PayloadMode, negotiation, fallback
│   ├── provenance.rs   # Provenance tracking
│   └── trust.rs        # TrustDomain, policy checks
├── session_manager.rs  # Session cache and lifecycle
└── config.rs           # LdpAdapterConfig
```

## For Research Experiments

The experiment runner binary (in `experiments/`) creates its own JamJet runtime with LDP registered. This binary lives in `ldp-research`, not in JamJet:

```rust
// experiments/src/main.rs
let mut registry = default_protocol_registry();
register_ldp(&mut registry, Some(config));
// ... run experiments against LDP, A2A, MCP baselines ...
```
