# LDP: LLM Delegate Protocol

An identity-aware communication protocol for multi-agent LLM systems.

LDP extends service-oriented agent protocols (like [A2A](https://github.com/a2aproject/A2A) and [MCP](https://modelcontextprotocol.io/)) with AI-native primitives: rich delegate identity, progressive payload modes, governed sessions, structured provenance, and trust domains.

**Paper:** [arXiv:2603.08852](https://arxiv.org/abs/2603.08852) · [PDF](https://arxiv.org/pdf/2603.08852)

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

## Quick Start

### Python — Run an LDP delegate in 30 seconds

```bash
cd examples/python_sdk
pip install -r requirements.txt

# Terminal 1: Start a delegate
python ldp_delegate.py

# Terminal 2: Discover and invoke it
python ldp_client.py
```

**Output:**
```
1. Discovering delegate...
   Name: Research Analyst
   Model: claude claude-sonnet-4-6
   Trust: research.internal
   Capabilities: ['reasoning', 'summarization']

2. Establishing session...
   Session established: a3f2c1d8... (mode: SemanticFrame)

3. Submitting reasoning task...
   Output: {"text": "..."}
   Provenance:
     produced_by: ldp:delegate:analyst-01
     model: claude-sonnet-4-6
     confidence: 0.85
     verified: false
```

### Rust — Register in JamJet

```rust
use ldp_protocol::register_ldp;

let mut registry = default_protocol_registry(); // MCP, A2A built-in
register_ldp(&mut registry, None);              // LDP plugged in

// Now ldp:// URLs route through LDP with full session management
let caps = registry.discover("ldp://analyst.internal:8090").await?;
let handle = registry.invoke("ldp://analyst.internal:8090", task).await?;
```

### Python — Multi-delegate routing

```python
from ldp_client import LdpClient

client = LdpClient()

# Discover multiple delegates
delegates = [
    await client.discover("http://fast-model:8091"),
    await client.discover("http://deep-model:8092"),
]

# Route by quality score (impossible with skill-name-only protocols)
best = max(delegates, key=lambda d:
    next(c["quality"]["quality_score"]
         for c in d["capabilities"] if c["name"] == "reasoning"))

result = await client.submit_task(
    f"http://localhost:{best['endpoint'].split(':')[-1]}",
    skill="reasoning",
    input_data={"prompt": "Analyze the tradeoffs..."},
)

# Every result carries provenance
print(result["provenance"]["produced_by"])   # ldp:delegate:deep-01
print(result["provenance"]["verified"])       # True/False
```

See [`examples/python_sdk/multi_delegate_routing.py`](examples/python_sdk/multi_delegate_routing.py) for the full routing example.

## Protocol Overview

### 1. Delegate Identity Cards

Every LDP delegate publishes a rich identity card at `GET /ldp/identity`:

```json
{
  "delegate_id": "ldp:delegate:qwen3-8b-reasoning",
  "model_family": "qwen",
  "model_version": "qwen3-8b-2026.01",
  "reasoning_profile": "deep-analytical",
  "cost_profile": "medium",
  "context_window": 32768,
  "trust_domain": {"name": "research.internal", "allow_cross_domain": false},
  "capabilities": [
    {
      "name": "reasoning",
      "quality": {"quality_score": 0.85, "latency_p50_ms": 5000, "cost_per_call_usd": 0.015}
    }
  ],
  "supported_payload_modes": ["SemanticFrame", "Text"]
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

Delegates negotiate the richest mutually supported mode during session establishment. If a mode fails, the protocol automatically falls back: Mode N → Mode N-1 → ... → Mode 0.

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
  "payload_mode_used": "SemanticFrame",
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

## HTTP API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/ldp/identity` | GET | Delegate's identity card |
| `/ldp/capabilities` | GET | Capability manifest |
| `/ldp/messages` | POST | Send/receive LDP protocol messages |

### Message Types

| Type | Direction | Purpose |
|---|---|---|
| `HELLO` | → | Initiate handshake with supported modes |
| `CAPABILITY_MANIFEST` | ← | Declare capabilities |
| `SESSION_PROPOSE` | → | Propose session with config |
| `SESSION_ACCEPT` | ← | Accept with negotiated mode |
| `SESSION_REJECT` | ← | Reject with reason |
| `TASK_SUBMIT` | → | Submit task within session |
| `TASK_UPDATE` | ← | Progress update |
| `TASK_RESULT` | ← | Result with provenance |
| `TASK_FAILED` | ← | Failure with error |
| `TASK_CANCEL` | → | Cancel in-flight task |
| `SESSION_CLOSE` | ↔ | Terminate session |

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
Remote LDP Delegate (LdpServer)
```

### Project Structure

```
ldp-protocol/
├── src/
│   ├── lib.rs              # Public API exports
│   ├── adapter.rs          # ProtocolAdapter implementation
│   ├── plugin.rs           # JamJet plugin registration
│   ├── client.rs           # LDP HTTP client
│   ├── server.rs           # LDP server + test helpers
│   ├── session_manager.rs  # Session cache and lifecycle
│   ├── config.rs           # Adapter configuration
│   └── types/
│       ├── identity.rs     # LdpIdentityCard
│       ├── capability.rs   # Capabilities with quality/cost/latency hints
│       ├── session.rs      # Session state and negotiation
│       ├── messages.rs     # LDP message envelope and body types
│       ├── payload.rs      # PayloadMode, negotiation, fallback
│       ├── provenance.rs   # Provenance tracking
│       └── trust.rs        # TrustDomain, policy checks
├── examples/
│   ├── python_sdk/         # Python examples (delegate, client, routing)
│   ├── identity_card.json  # Example identity card
│   ├── session_flow.json   # Message sequence example
│   └── rust_quickstart.rs  # Rust integration example
├── tests/
│   └── ldp_integration.rs  # End-to-end integration tests
└── docs/
    ├── RFC.md              # Formal protocol specification
    └── DESIGN.md           # JamJet integration architecture
```

### Building

```bash
# Build
cargo build

# Run tests
cargo test

# Run Rust example
cargo run --example rust_quickstart
```

## Documentation

- **[Protocol Specification (RFC)](docs/RFC.md)** — Formal protocol specification
- **[Design Document](docs/DESIGN.md)** — JamJet integration architecture
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
