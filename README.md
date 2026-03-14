# LDP: LLM Delegate Protocol

An identity-aware communication protocol for multi-agent LLM systems.

LDP extends service-oriented agent protocols (like [A2A](https://github.com/a2aproject/A2A) and [MCP](https://modelcontextprotocol.io/)) with AI-native primitives: rich delegate identity, progressive payload modes, governed sessions, structured provenance, and trust domains.

**Install:** `pip install ldp-protocol` · **Website:** [ldp.sunilprakash.com](https://ldp.sunilprakash.com) · **Paper:** [arXiv:2603.08852](https://arxiv.org/abs/2603.08852) · [PDF](https://arxiv.org/pdf/2603.08852)

## Why LDP?

[A2A](https://github.com/a2aproject/A2A) handles agent-to-agent communication. [MCP](https://modelcontextprotocol.io/) handles agent-to-tool integration. LDP adds the **delegation intelligence layer** on top — the layer that decides *which* agent to route to, *how* to encode the payload, and *whether to trust* the result.

```
┌──────────────────────────────────────────┐
│  Delegation Intelligence — LDP           │
│  (identity, routing, provenance, trust)  │
├──────────────────────────────────────────┤
│  Agent Communication — A2A               │
├──────────────────────────────────────────┤
│  Tool Integration — MCP                  │
└──────────────────────────────────────────┘
```

LDP extends agent protocols with AI-native primitives:

- **Rich delegate identity** — model family, quality scores, reasoning profiles, cost/latency hints
- **Progressive payload modes** — negotiate encoding efficiency (37% token reduction with semantic frames)
- **Governed sessions** — persistent context eliminates re-transmitting conversation history
- **Structured provenance** — every response carries who produced it, confidence, and verification status
- **Trust domains** — protocol-level security boundaries beyond transport-level auth

## Quick Start

```bash
pip install ldp-protocol
```

### See it in action — Smart vs Blind Routing

```bash
python examples/demo_smart_routing.py
```

```
Discovered 3 delegates:

  Fast Agent       gemini-2.0-flash       quality=0.60  cost=$0.001  p50=200ms
  Balanced Agent   claude-sonnet-4-6      quality=0.82  cost=$0.008  p50=1200ms
  Deep Agent       claude-opus-4-6        quality=0.95  cost=$0.025  p50=3500ms

  Round 1: Blind Routing (skill-name only)

  Task (easy  )  ->  Deep Agent       cost=$0.025  latency=3496ms  <- overkill
  Task (medium)  ->  Deep Agent       cost=$0.025  latency=3493ms  <- expensive
  Task (hard  )  ->  Deep Agent       cost=$0.025  latency=3755ms  <- correct

  Total: $0.075  |  10,744ms  |  Avg quality: 0.95

  Round 2: LDP Routing (identity-aware)

  Task (easy  )  ->  Fast Agent       cost=$0.001  latency=200ms   <- right-sized
  Task (medium)  ->  Balanced Agent   cost=$0.008  latency=1108ms  <- right-sized
  Task (hard  )  ->  Deep Agent       cost=$0.025  latency=3582ms  <- right-sized

  Total: $0.034  |  4,890ms  |  Quality matched to task complexity

  Cost savings:    55% ($0.075 -> $0.034)
  Latency savings: 54% (10,744ms -> 4,890ms)

  Provenance (LDP exclusive):
    produced_by:  ldp:delegate:deep-01
    model:        claude-opus-4-6
    confidence:   0.91
    verified:     True
    payload_mode: semantic_frame (37% fewer tokens than text)
```

### Create a delegate

```python
from ldp_protocol import LdpDelegate, LdpCapability, QualityMetrics

class MyDelegate(LdpDelegate):
    async def handle_task(self, skill, input_data, task_id):
        return {"answer": "42"}, 0.95  # (output, confidence)

delegate = MyDelegate(
    delegate_id="ldp:delegate:my-agent",
    name="My Agent",
    model_family="claude",
    model_version="claude-sonnet-4-6",
    capabilities=[
        LdpCapability(
            name="reasoning",
            quality=QualityMetrics(quality_score=0.85, cost_per_call_usd=0.01),
        ),
    ],
)
delegate.run(port=8090)  # requires: pip install ldp-protocol[server]
```

### Discover and invoke

```python
from ldp_protocol import LdpClient

async with LdpClient() as client:
    identity = await client.discover("http://localhost:8090")
    print(f"Found: {identity.name} ({identity.model_family})")
    print(f"Quality: {identity.quality_score('reasoning')}")

    result = await client.submit_task(
        "http://localhost:8090",
        skill="reasoning",
        input_data={"prompt": "Analyze the tradeoffs..."},
    )
    print(result["output"])
    print(result["provenance"])  # who produced it, confidence, verified
```

### Multi-delegate routing

```python
from ldp_protocol import LdpRouter, RoutingStrategy

async with LdpRouter() as router:
    await router.discover_delegates([
        "http://fast-model:8091",
        "http://deep-model:8092",
    ])

    # Route by quality, cost, latency, or balanced score
    result = await router.route_and_submit(
        skill="reasoning",
        input_data={"prompt": "Complex analysis..."},
        strategy=RoutingStrategy.QUALITY,
    )
    print(f"Routed to: {result['routed_to']['name']}")
    print(f"Provenance: {result['provenance']}")
```

## Protocol Overview

### 1. Delegate Identity Cards

Every LDP delegate publishes a rich identity card at `GET /ldp/identity`:

```json
{
  "delegate_id": "ldp:delegate:analyst-01",
  "model_family": "claude",
  "model_version": "claude-sonnet-4-6",
  "reasoning_profile": "deep-analytical",
  "cost_profile": "medium",
  "context_window": 200000,
  "trust_domain": {"name": "research.internal", "allow_cross_domain": false},
  "capabilities": [
    {
      "name": "reasoning",
      "quality": {"quality_score": 0.85, "latency_p50_ms": 1200, "cost_per_call_usd": 0.008}
    }
  ],
  "supported_payload_modes": ["semantic_frame", "text"]
}
```

This enables **metadata-aware routing**: send easy tasks to fast, cheap models and hard tasks to capable, expensive models — decisions impossible with skill-name-only matching.

### 2. Progressive Payload Modes

| Mode | Name | Status | Description |
|------|------|--------|-------------|
| 0 | Text | Implemented | Natural language. Universal fallback. |
| 1 | Semantic Frame | Implemented | Typed structured JSON. 37% fewer tokens than text. |
| 2 | Embedding Hints | Specified | Vector representations for semantic routing. |
| 3 | Semantic Graph | Specified | Structured relationship representations. |
| 4 | Latent Capsules | Future | Compressed machine-native semantic packets. |
| 5 | Cache Slices | Future | Execution-state transfer between compatible models. |

Delegates negotiate the richest mutually supported mode during session establishment. If a mode fails, the protocol automatically falls back: Mode N -> Mode N-1 -> ... -> Mode 0.

### 3. Governed Sessions

Unlike stateless protocols, LDP sessions maintain persistent context:

```
HELLO -> CAPABILITY_MANIFEST -> SESSION_PROPOSE -> SESSION_ACCEPT
  -> TASK_SUBMIT / TASK_UPDATE / TASK_RESULT (within session context)
  -> SESSION_CLOSE
```

Sessions eliminate re-transmitting conversation history, reducing token overhead that grows quadratically with conversation length.

### 4. Structured Provenance

Every task result carries provenance metadata:

```json
{
  "produced_by": "ldp:delegate:analyst-01",
  "model_version": "claude-sonnet-4-6",
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

## HTTP API

| Endpoint | Method | Description |
|---|---|---|
| `/ldp/identity` | GET | Delegate's identity card |
| `/ldp/capabilities` | GET | Capability manifest |
| `/ldp/messages` | POST | Send/receive LDP protocol messages |

### Message Types

| Type | Direction | Purpose |
|---|---|---|
| `HELLO` | -> | Initiate handshake with supported modes |
| `CAPABILITY_MANIFEST` | <- | Declare capabilities |
| `SESSION_PROPOSE` | -> | Propose session with config |
| `SESSION_ACCEPT` | <- | Accept with negotiated mode |
| `SESSION_REJECT` | <- | Reject with reason |
| `TASK_SUBMIT` | -> | Submit task within session |
| `TASK_UPDATE` | <- | Progress update |
| `TASK_RESULT` | <- | Result with provenance |
| `TASK_FAILED` | <- | Failure with error |
| `TASK_CANCEL` | -> | Cancel in-flight task |
| `SESSION_CLOSE` | <-> | Terminate session |

## SDKs

### Python (primary)

```bash
pip install ldp-protocol
```

The Python SDK includes: pydantic models for all protocol types, async client with session management, delegate base class with optional Starlette server, and multi-strategy router.

See [`sdk/python/`](sdk/python/) for full documentation.

### Rust (reference implementation)

The Rust crate serves as the reference implementation — useful for production deployments and native integration with the [JamJet](https://github.com/jamjet-labs/jamjet) agent runtime.

```bash
cargo build
cargo test   # 17 tests (10 unit + 7 integration)
```

#### Standalone adapter

```rust
use ldp_protocol::{LdpAdapter, LdpAdapterConfig};
use ldp_protocol::protocol::{ProtocolAdapter, TaskRequest};
use serde_json::json;

let adapter = LdpAdapter::new(LdpAdapterConfig {
    delegate_id: "ldp:delegate:my-orchestrator".into(),
    ..Default::default()
});

// Discover a remote delegate
let caps = adapter.discover("http://localhost:8090").await?;
println!("Found: {} with {} skills", caps.name, caps.skills.len());

// Submit a task
let handle = adapter.invoke("http://localhost:8090", TaskRequest {
    skill: "reasoning".into(),
    input: json!({"prompt": "Analyze the tradeoffs..."}),
}).await?;
```

#### With a protocol registry

```rust
use ldp_protocol::{register_ldp, LdpAdapterConfig};
use ldp_protocol::protocol::ProtocolRegistry;

let mut registry = ProtocolRegistry::new();
register_ldp(&mut registry, Some(LdpAdapterConfig::default()));

// ldp:// URLs are now routed to the LDP adapter
let adapter = registry.adapter_for_url("ldp://delegate.example.com").unwrap();
let caps = adapter.discover("http://delegate.example.com").await?;
```

#### JamJet integration

Enable the `jamjet` feature to plug LDP into JamJet's runtime alongside MCP and A2A:

```toml
[dependencies]
ldp-protocol = { version = "0.1", features = ["jamjet"] }
```

```rust
use ldp_protocol::plugin::register_ldp_jamjet;

let mut registry = jamjet_protocols::ProtocolRegistry::new();
// MCP, A2A registered by JamJet...
register_ldp_jamjet(&mut registry, None);  // LDP plugged in

// Now ldp:// URLs route through LDP with full session management
```

## Project Structure

```
ldp-protocol/
├── sdk/python/                 # Python SDK (primary)
│   ├── src/ldp_protocol/       # Package source
│   │   ├── types/              # Pydantic models (identity, capability, etc.)
│   │   ├── client.py           # Async HTTP client
│   │   ├── delegate.py         # Delegate base class
│   │   └── router.py           # Multi-strategy routing
│   └── tests/                  # 29 tests
├── src/                        # Rust reference implementation
│   ├── protocol.rs             # Standalone protocol abstractions
│   ├── adapter.rs              # ProtocolAdapter implementation
│   ├── client.rs               # LDP HTTP client
│   ├── server.rs               # LDP server
│   ├── session_manager.rs      # Session lifecycle
│   └── types/                  # Protocol type definitions
├── examples/
│   ├── demo_smart_routing.py   # Killer demo: smart vs blind routing
│   └── python_sdk/             # Additional Python examples
├── tests/
│   └── ldp_integration.rs      # Rust integration tests (17 tests)
└── docs/
    ├── RFC.md                  # Protocol specification
    └── DESIGN.md               # Architecture documentation
```

## Documentation

- **[Protocol Specification (RFC)](docs/RFC.md)** — Formal protocol specification
- **[Python SDK](sdk/python/)** — Python package documentation
- **[Design Document](docs/DESIGN.md)** — Architecture and integration docs
- **[Research Paper](https://arxiv.org/abs/2603.08852)** — arXiv:2603.08852
- **[Experiment Code](https://github.com/sunilp/ldp-research)** — Reproduce the empirical evaluation

## Research

LDP is backed by empirical research comparing it against A2A and random baselines. Key findings:

- **Routing:** Identity-aware routing achieves ~12x lower latency on easy tasks through delegate specialization
- **Payload:** Semantic frames reduce token count by 37% (p=0.031) with no observed quality loss
- **Provenance:** Noisy confidence signals degrade quality below the no-provenance baseline — verification matters
- **Sessions:** Governed sessions eliminate quadratic token overhead in multi-round delegation

### Related

- **[DCI (Deliberative Collective Intelligence)](https://github.com/sunilp/dci-research)** — [arXiv:2603.11781](https://arxiv.org/abs/2603.11781) · DCI provides the reasoning layer; LDP provides the delegation protocol
- [Why Multi-Agent AI Systems Need Identity-Aware Routing](https://sunilprakash.com/writing/ldp-protocol/)
- [From Debate to Deliberation: When Multi-Agent Reasoning Needs Structure](https://sunilprakash.com/writing/deliberative-collective-intelligence/)

## Citation

```bibtex
@article{prakash2026ldp,
  title={LDP: An Identity-Aware Communication Protocol
         for Multi-Agent LLM Systems},
  author={Prakash, Sunil},
  journal={arXiv preprint arXiv:2603.08852},
  year={2026}
}
```

## License

Apache-2.0
