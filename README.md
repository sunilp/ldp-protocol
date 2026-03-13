# LDP: LLM Delegate Protocol

An identity-aware communication protocol for multi-agent LLM systems.

LDP extends service-oriented agent protocols (like [A2A](https://github.com/a2aproject/A2A) and [MCP](https://modelcontextprotocol.io/)) with AI-native primitives: rich delegate identity, progressive payload modes, governed sessions, structured provenance, and trust domains.

## Why LDP?

Current agent protocols treat AI agents as opaque services — exposing only a name, description, and skill list. This discards information critical to effective delegation:

| What a router needs to know | A2A | MCP | LDP |
|---|:---:|:---:|:---:|
| Model family and version | - | - | Yes |
| Quality hints (0-1 score) | - | - | Yes |
| Reasoning profile | - | - | Yes |
| Cost/latency characteristics | - | - | Yes |
| Payload format negotiation | - | - | Yes |
| Multi-round sessions | - | - | Yes |
| Structured provenance | - | - | Yes |
| Trust domain enforcement | - | - | Yes |

## Protocol Overview

### 1. Delegate Identity Cards

Every LDP delegate publishes a rich identity card:

```json
{
  "delegate_id": "ldp:delegate:qwen3-8b-reasoning",
  "model_family": "qwen",
  "model_version": "qwen3-8b-2026.01",
  "reasoning_profile": "deep-analytical",
  "cost_profile": "medium",
  "context_window": 32768,
  "trust_domain": "research.internal",
  "capabilities": [
    {
      "name": "reasoning",
      "quality_hint": 0.85,
      "latency_hint_ms_p50": 5000,
      "cost_hint": "medium"
    }
  ],
  "supported_payload_modes": ["semantic_frame", "text"]
}
```

This enables **metadata-aware routing**: send easy tasks to fast, cheap models and hard tasks to capable, expensive models — decisions impossible with skill-name-only matching.

### 2. Progressive Payload Modes

LDP defines payload modes of increasing efficiency:

| Mode | Name | Status | Description |
|------|------|--------|-------------|
| 0 | Text | Implemented | Natural language. Universal fallback. |
| 1 | Semantic Frame | Implemented | Typed structured JSON. 37% fewer tokens than text. |
| 2 | Embedding Hints | Specified | Vector representations for semantic routing. |
| 3 | Semantic Graph | Specified | Structured relationship representations. |
| 4 | Latent Capsules | Future | Compressed machine-native semantic packets. |
| 5 | Cache Slices | Future | Execution-state transfer between compatible models. |

Delegates negotiate the richest mutually supported mode during session establishment. If a mode fails mid-exchange, the protocol automatically falls back: Mode N → Mode N-1 → ... → Mode 0.

### 3. Governed Sessions

Unlike stateless protocols, LDP sessions maintain persistent context:

```
HELLO → CAPABILITY_MANIFEST → SESSION_PROPOSE → SESSION_ACCEPT
  → TASK_SUBMIT / TASK_UPDATE / TASK_RESULT (within session context)
  → SESSION_CLOSE
```

Sessions eliminate re-transmitting conversation history, reducing token overhead that grows quadratically with conversation length.

### 4. Structured Provenance

Every task result carries provenance metadata:

```json
{
  "produced_by": "ldp:delegate:qwen3-8b",
  "model_version": "qwen3-8b-2026.01",
  "payload_mode_used": "semantic_frame",
  "confidence": 0.84,
  "verified": true
}
```

Downstream consumers can weight outputs by source reliability. Critically, provenance includes verification status — unverified confidence signals can be harmful (see [research findings](https://github.com/sunilp/ldp-research)).

### 5. Trust Domains

Security boundaries enforced at the protocol level:

- **Message level:** Per-message signatures, nonces, replay protection
- **Session level:** Trust domain compatibility checks during establishment
- **Policy level:** Capability scope, jurisdiction compliance, cost limits

## Implementation

This repository contains the Rust reference implementation of LDP as a plugin adapter for the [JamJet](https://github.com/jamjet-labs/jamjet) agent runtime.

### Architecture

```
JamJet Workflow Engine
  ↓ discover / invoke / stream / status / cancel
LdpAdapter (ProtocolAdapter impl)
  ↓ manages sessions transparently
SessionManager
  ↓ HELLO → SESSION_PROPOSE → SESSION_ACCEPT → TASK_SUBMIT
LdpClient (HTTP)
  ↓
Remote LDP Delegate
```

### Integration

LDP registers at runtime with zero modifications to JamJet:

```rust
use jamjet_ldp::register_ldp;

let mut registry = default_protocol_registry(); // MCP, A2A built-in
register_ldp(&mut registry, None);              // LDP plugged in
```

URL-based dispatch routes `ldp://` prefixed addresses to the LDP adapter.

### Project Structure

```
src/
├── lib.rs              # Public API
├── adapter.rs          # ProtocolAdapter implementation
├── plugin.rs           # JamJet plugin registration
├── client.rs           # LDP HTTP client
├── server.rs           # LDP server (identity serving)
├── session_manager.rs  # Session cache and lifecycle
├── config.rs           # Adapter configuration
└── types/
    ├── identity.rs     # LdpIdentityCard
    ├── capability.rs   # Capabilities with quality/latency/cost hints
    ├── session.rs      # Session state and negotiation
    ├── messages.rs     # LDP message envelope and body types
    ├── payload.rs      # PayloadMode, negotiation, fallback
    ├── provenance.rs   # Provenance tracking
    └── trust.rs        # TrustDomain, policy checks
```

## Documentation

- **[Protocol Specification (RFC)](docs/RFC.md)** — Formal protocol specification
- **[Design Document](docs/DESIGN.md)** — JamJet integration architecture
- **[Research Paper](https://arxiv.org/abs/2603.08852v1)** — LDP: An Identity-Aware Protocol for Multi-Agent LLM Systems (arXiv:2603.08852)
- **[Experiment Code](https://github.com/sunilp/ldp-research)** — Reproduce the empirical evaluation

## Research

LDP is backed by empirical research comparing it against A2A and random baselines. Key findings:

- **Routing:** Identity-aware routing achieves ~12x lower latency on easy tasks through delegate specialization
- **Payload:** Semantic frames reduce token count by 37% (p=0.031) with no observed quality loss
- **Provenance:** Noisy confidence signals degrade quality below the no-provenance baseline — verification matters
- **Sessions:** Governed sessions eliminate quadratic token overhead in multi-round delegation

Full paper: [arXiv:2603.08852](https://arxiv.org/abs/2603.08852v1) | Experiment code: [sunilp/ldp-research](https://github.com/sunilp/ldp-research)

### Related Writing

- [Why Multi-Agent AI Systems Need Identity-Aware Routing](https://sunilprakash.com/writing/ldp-protocol/)
- [From Debate to Deliberation: When Multi-Agent Reasoning Needs Structure](https://sunilprakash.com/writing/deliberative-collective-intelligence/)

## License

Apache-2.0
