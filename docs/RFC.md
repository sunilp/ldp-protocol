# LDP Protocol Specification (RFC)

**LLM Delegate Protocol — Version 0.1**

**Status:** Draft
**Author:** Sunil Prakash
**Date:** 2026-03-09

---

## 1. Introduction

The LLM Delegate Protocol (LDP) is a communication protocol for multi-agent LLM systems. It enables AI agents to discover, negotiate with, delegate to, and verify other AI agents using structured identity metadata, progressive payload formats, governed sessions, provenance tracking, and trust domain enforcement.

### 1.1 Motivation

Existing agent protocols (A2A, MCP) treat AI agents as opaque services. LDP is designed around the observation that AI agents are **not** opaque — they are heterogeneous models with measurable properties (quality, cost, latency, reasoning style) that should inform delegation decisions.

### 1.2 Terminology

- **Delegate**: An AI agent that accepts delegated tasks via LDP
- **Router**: A component that selects delegates based on identity metadata
- **Session**: A governed, persistent context for multi-round delegation
- **Trust Domain**: A named security boundary within which identity and policy guarantees are recognized
- **Payload Mode**: A format for encoding task inputs and outputs between delegates

### 1.3 Protocol Layers

```
┌─────────────────────────────────┐
│  Application (routing, policy)  │
├─────────────────────────────────┤
│  Session (lifecycle, context)   │
├─────────────────────────────────┤
│  Message (envelope, payload)    │
├─────────────────────────────────┤
│  Transport (HTTP/S, WebSocket)  │
└─────────────────────────────────┘
```

## 2. Identity Model

### 2.1 Delegate Identity Card

Every LDP delegate MUST publish an identity card containing the following fields:

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `delegate_id` | string | Unique identifier (format: `ldp:delegate:<name>`) |
| `name` | string | Human-readable name |
| `model_family` | string | Model family (e.g., "qwen", "llama", "claude") |
| `model_version` | string | Model version string |
| `trust_domain` | TrustDomain | Trust domain this delegate belongs to |
| `context_window` | uint64 | Maximum context window in tokens |
| `capabilities` | LdpCapability[] | List of capabilities with quality/cost metadata |
| `supported_payload_modes` | PayloadMode[] | Ordered list of supported payload modes |
| `endpoint` | string | URL endpoint for the delegate |

#### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Purpose description |
| `weights_fingerprint` | string | SHA-256 hash of model weights |
| `reasoning_profile` | string | Qualitative reasoning descriptor (e.g., "deep-analytical", "fast-practical") |
| `cost_profile` | string | Cost tier: "low", "medium", "high" |
| `latency_profile` | string | Latency characteristics (e.g., "p50:2000ms") |
| `jurisdiction` | string | Jurisdictional constraints (e.g., "us-east", "eu-west") |
| `metadata` | map<string, string> | Additional key-value metadata |

### 2.2 Capabilities

Each capability entry carries quality and cost metadata:

```json
{
  "name": "reasoning",
  "quality_hint": 0.85,
  "latency_hint_ms_p50": 5000,
  "cost_hint": "medium"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Capability name |
| `quality_hint` | float (0.0-1.0) | Quality score for this capability |
| `latency_hint_ms_p50` | uint64 | Median latency in milliseconds |
| `cost_hint` | string | Cost tier: "low", "medium", "high" |

### 2.3 Identity Discovery

Delegates MUST serve their identity card at `GET <endpoint>/.well-known/ldp-identity`.

Response: `200 OK` with `Content-Type: application/json` body containing the full `LdpIdentityCard`.

## 3. Message Format

### 3.1 Message Envelope

All LDP messages are wrapped in an envelope:

```json
{
  "message_id": "<uuid>",
  "session_id": "<uuid>",
  "from": "<delegate_id>",
  "to": "<delegate_id>",
  "body": { "type": "<MESSAGE_TYPE>", ... },
  "payload_mode": "<mode>",
  "timestamp": "<ISO 8601>",
  "provenance": null
}
```

### 3.2 Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `HELLO` | Initiator → Responder | Initial handshake with supported modes |
| `CAPABILITY_MANIFEST` | Responder → Initiator | Capability declaration |
| `SESSION_PROPOSE` | Initiator → Responder | Propose session with configuration |
| `SESSION_ACCEPT` | Responder → Initiator | Accept session, confirm negotiated mode |
| `SESSION_REJECT` | Responder → Initiator | Reject session with reason |
| `TASK_SUBMIT` | Initiator → Responder | Submit task within session |
| `TASK_UPDATE` | Responder → Initiator | Task progress update |
| `TASK_RESULT` | Responder → Initiator | Task completion with provenance |
| `TASK_FAILED` | Responder → Initiator | Task failure with error |
| `TASK_CANCEL` | Initiator → Responder | Cancel a running task |
| `ATTESTATION` | Either | Trust attestation signal |
| `SESSION_CLOSE` | Either | Terminate session |

### 3.3 Message Body Schemas

#### HELLO

```json
{
  "type": "HELLO",
  "delegate_id": "ldp:delegate:router-alpha",
  "supported_modes": ["semantic_frame", "text"]
}
```

#### SESSION_PROPOSE

```json
{
  "type": "SESSION_PROPOSE",
  "config": {
    "preferred_payload_modes": ["semantic_frame", "text"],
    "ttl_secs": 3600,
    "required_trust_domain": "research.internal"
  }
}
```

#### SESSION_ACCEPT

```json
{
  "type": "SESSION_ACCEPT",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "negotiated_mode": "semantic_frame"
}
```

#### TASK_SUBMIT

```json
{
  "type": "TASK_SUBMIT",
  "task_id": "task-001",
  "skill": "reasoning",
  "input": {
    "task_type": "analysis",
    "instruction": "Analyze the tradeoffs...",
    "expected_output_format": "structured_analysis"
  }
}
```

#### TASK_RESULT

```json
{
  "type": "TASK_RESULT",
  "task_id": "task-001",
  "output": { "analysis": "..." },
  "provenance": {
    "produced_by": "ldp:delegate:qwen3-8b",
    "model_version": "qwen3-8b-2026.01",
    "payload_mode_used": "semantic_frame",
    "confidence": 0.84,
    "verified": true
  }
}
```

## 4. Payload Modes

### 4.1 Mode Definitions

| Mode | Name | Wire Value | Status |
|------|------|-----------|--------|
| 0 | Text | `text` | Required |
| 1 | Semantic Frame | `semantic_frame` | Recommended |
| 2 | Embedding Hints | `embedding_hints` | Optional |
| 3 | Semantic Graph | `semantic_graph` | Optional |
| 4 | Latent Capsules | `latent_capsules` | Future |
| 5 | Cache Slices | `cache_slices` | Future |

Every delegate MUST support Mode 0 (Text).

### 4.2 Negotiation

During session establishment, the initiator and responder exchange supported modes. The negotiation algorithm selects the highest-preference implemented mode supported by both parties:

```
1. For each mode in initiator's preference list (highest first):
   a. If mode is implemented AND responder supports it → select this mode
2. If no common implemented mode found → fall back to Mode 0 (Text)
3. Build fallback chain from remaining common modes with lower mode numbers
```

### 4.3 Fallback

If a payload mode fails mid-session (e.g., schema validation error), the protocol falls back through the negotiated fallback chain:

```
Mode N (fails) → Mode N-1 → ... → Mode 0 (Text)
```

Fallback is automatic and transparent. The session continues at the lower mode. Delegates MUST NOT terminate a session due to a payload mode failure if a fallback mode is available.

### 4.4 Semantic Frame Format (Mode 1)

Semantic frames use typed JSON fields to reduce verbosity:

```json
{
  "task_type": "classification",
  "instruction": "Classify sentiment",
  "input": "The product arrived on time...",
  "expected_output_format": "label+justification",
  "labels": ["positive", "negative", "neutral"]
}
```

Required fields: `task_type`, `instruction`. All other fields are optional.

## 5. Sessions

### 5.1 Session Lifecycle

```
INITIATING → PROPOSED → ACTIVE → CLOSED
                ↓          ↓
              FAILED    SUSPENDED → ACTIVE (resume)
```

### 5.2 Session Establishment

```
Initiator                         Responder
    │                                 │
    │──── HELLO ─────────────────────>│
    │<─── CAPABILITY_MANIFEST ────────│
    │──── SESSION_PROPOSE ───────────>│
    │<─── SESSION_ACCEPT ─────────────│
    │                                 │
    │  (session is now ACTIVE)        │
    │                                 │
    │──── TASK_SUBMIT ───────────────>│
    │<─── TASK_UPDATE (optional) ─────│
    │<─── TASK_RESULT ────────────────│
    │                                 │
    │──── SESSION_CLOSE ─────────────>│
```

### 5.3 Session Context

Sessions maintain server-side context. Within an active session:

- Conversation history is preserved — no need to re-send prior context
- Payload mode is fixed (unless fallback occurs)
- Trust domain is validated once at establishment
- Budget/cost tracking persists across tasks

### 5.4 Session Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `preferred_payload_modes` | PayloadMode[] | [SemanticFrame, Text] | Mode preference list |
| `ttl_secs` | uint64 | 3600 | Session timeout (seconds of inactivity) |
| `required_trust_domain` | string? | null | Required trust domain for the responder |

## 6. Provenance

### 6.1 Provenance Record

Every TASK_RESULT message MUST include a provenance record:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `produced_by` | string | Yes | Delegate ID that produced the result |
| `model_version` | string | Yes | Model version used |
| `payload_mode_used` | PayloadMode | Yes | Payload mode for this exchange |
| `confidence` | float? | No | Self-reported confidence (0.0-1.0) |
| `verified` | bool | Yes | Whether the result has been independently verified |
| `session_id` | string? | No | Session in which result was produced |
| `timestamp` | string? | No | ISO 8601 timestamp of production |

### 6.2 Verification

The `verified` field indicates whether the result has been checked by an independent process (e.g., a second delegate, a rule-based validator, or a human reviewer). Consumers SHOULD treat unverified confidence scores with caution — empirical evidence shows that unverified confidence can degrade downstream decision quality.

## 7. Trust Domains

### 7.1 Domain Definition

A trust domain is a named security boundary:

```json
{
  "name": "research.internal",
  "allow_cross_domain": false,
  "trusted_peers": []
}
```

### 7.2 Trust Checks

Trust domain compatibility is checked during session establishment (before SESSION_ACCEPT):

1. If the initiator specifies `required_trust_domain`, the responder's domain MUST match
2. If `allow_cross_domain` is false, cross-domain sessions are rejected
3. If `allow_cross_domain` is true, the initiator's domain MUST be in `trusted_peers`

### 7.3 Security Enforcement Levels

| Level | Mechanism | Description |
|-------|-----------|-------------|
| Message | Envelope fields | Message ID, session ID, timestamp for replay detection |
| Session | Trust domain check | Domain compatibility validated at establishment |
| Policy | Capability manifest | Task validated against declared capabilities |

## 8. Transport

### 8.1 HTTP Binding

LDP messages are transported over HTTP/S:

- **Discovery:** `GET <endpoint>/.well-known/ldp-identity` → Identity card
- **Messages:** `POST <endpoint>/ldp/messages` → LDP envelope in JSON body
- **Streaming:** `POST <endpoint>/ldp/stream` → Server-sent events (SSE) for TASK_UPDATE

### 8.2 Content Type

All LDP messages use `Content-Type: application/json`.

### 8.3 Authentication

LDP delegates SHOULD use mutual TLS or bearer tokens for transport-level authentication. Trust domain enforcement provides an additional application-level security layer.

## 9. Interoperability

### 9.1 AgentCard Mapping

For runtimes that use agent cards (e.g., JamJet), LDP identity fields are stored as prefixed labels:

| LDP Field | Label Key |
|-----------|-----------|
| delegate_id | `ldp.delegate_id` |
| model_family | `ldp.model_family` |
| model_version | `ldp.model_version` |
| trust_domain | `ldp.trust_domain` |
| context_window | `ldp.context_window` |
| weights_fingerprint | `ldp.weights_fingerprint` |
| reasoning_profile | `ldp.reasoning_profile` |
| cost_profile | `ldp.cost_profile` |
| latency_profile | `ldp.latency_profile` |
| jurisdiction | `ldp.jurisdiction` |
| supported_payload_modes | `ldp.payload_modes` (comma-separated) |

### 9.2 Coexistence with A2A and MCP

LDP is designed to coexist with A2A and MCP in the same runtime. URL-based dispatch (`ldp://` prefix) routes to the LDP adapter while `a2a://` and `mcp://` route to their respective adapters.

## 10. Conformance

### 10.1 Required

A conformant LDP implementation MUST:

1. Publish an identity card at `/.well-known/ldp-identity`
2. Support Mode 0 (Text) payload
3. Include provenance in all TASK_RESULT messages
4. Validate trust domain compatibility during session establishment
5. Implement the full session lifecycle (HELLO through SESSION_CLOSE)

### 10.2 Recommended

A conformant LDP implementation SHOULD:

1. Support Mode 1 (Semantic Frame) payload
2. Implement payload mode fallback
3. Support session TTL and expiration
4. Include confidence scores in provenance (when available)

---

## Appendix A: JSON Schema

Full JSON schemas for all LDP types are available in the reference implementation: [`src/types/`](../src/types/).

## Appendix B: Adoption Profiles

| Profile | Features | Use Case |
|---------|----------|----------|
| A (Basic) | Identity cards + text payloads + signed messages | Immediate routing benefit, minimal overhead |
| B (Enterprise) | + Provenance tracking + policy enforcement | Regulated domains, audit requirements |
| C (High-Performance) | + Payload negotiation + session management | High-volume systems, cost optimization at scale |
