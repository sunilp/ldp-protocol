# LDP Phase 1 Hardening + Ecosystem Launch

**Date:** 2026-03-22
**Version:** v0.3.0 (target release)
**Status:** Approved design

## Overview

This spec covers completing Phase 1 hardening (5 features) and launching LDP's ecosystem presence (CI/CD, conformance suite, crates.io, OpenAPI, CHANGELOG, tagged release). The approach is interleaved: CI/CD goes first as a safety net, then each hardening feature ships with conformance tests, followed by ecosystem artifacts and publishing.

## Execution Order

```
Phase A: Foundation
  1. CI/CD (ci.yml + release.yml)
  2. CHANGELOG.md (retroactive + ongoing)

Phase B: Hardening (each with conformance tests)
  3. Replay detection
  4. Bearer token auth
  5. Trust domain Rules #2-3
  6. Session TTL expiration
  7. SSE streaming

Phase C: Ecosystem
  8. OpenAPI spec
  9. Conformance test suite CLI
  10. crates.io publish
  11. Tag v0.3.0 release
  12. Blog post

Dependencies:
  - 3-7 are independent (parallelizable)
  - 8-9 need 3-7 complete
  - 10-12 need everything else
```

---

## 1. CI/CD Setup

Two GitHub Actions workflows.

### ci.yml (on PR + push to main)

```yaml
jobs:
  rust-check:
    - cargo fmt --check
    - cargo clippy -- -D warnings
    - cargo test
    - Matrix: stable + nightly

  python-check:
    - ruff check + ruff format --check
    - pytest
    - Matrix: Python 3.10, 3.11, 3.12, 3.13

  cross-sdk-compat:
    - Start Rust server in background
    - Run Python client tests against it
    - Validates signing interop, session handshake, protocol compat

  version-sync:
    - Fail if Cargo.toml and pyproject.toml versions diverge
```

### release.yml (on tag v*)

```yaml
jobs:
  ci: (reuse ci.yml)

  publish-pypi:
    - python -m build
    - twine upload (PYPI_API_TOKEN secret)

  publish-crates:
    - cargo publish (CARGO_REGISTRY_TOKEN secret)

  github-release:
    - Extract [Unreleased] from CHANGELOG.md
    - Create GitHub Release with extracted content
```

The **cross-sdk-compat** job is critical — it catches Rust/Python signing divergence and protocol drift.

---

## 2. Replay Detection

### Problem

Envelope has `message_id` and `timestamp` but nothing rejects duplicates or stale messages.

### Design

**Envelope change:** Add optional `nonce` field (16-byte random hex string) to `LdpEnvelope`. When signing is enabled, the sender MUST populate it.

**Signing compatibility:** The nonce is included in the canonical signing payload **only when non-null**. When nonce is `None` (e.g., messages from v0.2.0 clients), the signing payload is identical to the current format. This means v0.2.0 clients can still communicate with v0.3.0 servers when signing is enabled — their signatures will verify correctly. The `signature_algorithm` field remains `hmac-sha256` (no version bump needed).

**Server-side enforcement (when signing is enabled):**

```
On message receive:
  1. Reject if timestamp outside +/-60s window (configurable: replay_window_secs)
  2. Reject if (message_id, nonce) pair already seen
  3. Store seen pairs in bounded LRU cache (configurable: replay_cache_capacity, default 10,000)
  4. Return TASK_FAILED with error code REPLAY_DETECTED (FailureCategory: Security)
```

**Capacity sizing:** Deployers should set `replay_cache_capacity >= expected_messages_per_second * replay_window_secs` to avoid premature eviction. The default of 10,000 covers ~167 msg/s with a 60s window.

**Implementation:**

| Component | Location | Change |
|-----------|----------|--------|
| Rust ReplayGuard | `src/replay.rs` (new) | LRU cache + timestamp check |
| Rust server | `src/server.rs` | Call ReplayGuard before routing in `handle_message()` |
| Rust signing | `src/signing.rs` | Include nonce in canonical payload when non-null |
| Python ReplayGuard | `sdk/python/src/ldp_protocol/replay.py` (new) | Same logic |
| Python delegate | `delegate.py` | Call ReplayGuard in `handle_message()` |
| Python signing | `signing.py` | Include nonce in canonical payload when non-null |
| Rust error types | `src/types/error.rs` | Add `FailureCategory::Security` variant |
| Python error types | `types/error.py` | Add `Security` to FailureCategory enum |

**Backward compatibility:** If nonce is `None` and signing is disabled, replay detection is skipped. If nonce is `None` and signing is enabled, signature verification still works (nonce omitted from canonical payload), but replay detection is skipped for that message. This preserves full backward compatibility with v0.2.0 clients.

**Note on TASK_UPDATE signing:** The extended TASK_UPDATE signing payload (including `progress` and `message`) is NOT backward-compatible with v0.2.0 signed TASK_UPDATE messages. This is acceptable because TASK_UPDATE is rare in v0.2.0 flows (no streaming endpoint) and primarily used for the new SSE streaming feature.

**Tests:**

- Same message rejected on second send
- Stale timestamp (>60s) rejected
- Different nonce with same message_id accepted
- LRU eviction works (old message accepted after eviction)
- Unsigned messages bypass replay guard

---

## 3. Bearer Token Authentication

### Problem

HMAC signing proves message integrity but doesn't provide standard HTTP-level auth for API gateways and OAuth flows.

### Design

Bearer token auth operates at the **transport layer** (HTTP headers), separate from message signing (envelope layer). They can be used independently or together.

**Client side:**

```python
# Python
client = LdpClient(delegate_id="ldp:delegate:caller", bearer_token="sk-ldp-...")
# Sends: Authorization: Bearer sk-ldp-... on every HTTP request
```

```rust
// Rust
let config = LdpAdapterConfig {
    bearer_token: Some("sk-ldp-...".into()),
    ..Default::default()
};
```

**Server side:**

```python
delegate = MyDelegate(..., bearer_tokens={"sk-ldp-abc123", "sk-ldp-def456"})
# Rejects requests without valid Authorization header
```

**Enforcement flow:**

```
HTTP request arrives
  -> No bearer_tokens configured on server? Skip check.
  -> Missing Authorization header? HTTP 401 + WWW-Authenticate: Bearer
  -> Token not in allowed set? HTTP 403
  -> Valid? Proceed to handle_message()
```

**Implementation:**

| Component | Location | Change |
|-----------|----------|--------|
| Rust client | `src/client.rs` | Add Authorization header to reqwest calls |
| Rust server | `src/server.rs` | Middleware check before handle_message() |
| Rust config | `src/config.rs` | New `bearer_token` / `bearer_tokens` fields |
| Python client | `client.py` | Add header to httpx calls |
| Python delegate | `delegate.py` | Starlette middleware |

**What this is NOT:**

- Not an OAuth server (delegates don't issue tokens)
- Not token rotation/expiration (deployer's responsibility)
- Not a replacement for message signing (signing = integrity, bearer = caller identity)
- Not rate-limited at the protocol level — deployers should add rate limiting at their reverse proxy (nginx, API gateway) to protect against brute-force token guessing

**Tests:**

- Request without token -> 401
- Invalid token -> 403
- Valid token -> passes through
- No tokens configured -> all requests pass (backward compatible)
- Bearer + signing together works

---

## 4. SSE Streaming for TASK_UPDATE

### Problem

Task execution is synchronous. Client sends TASK_SUBMIT, blocks until TASK_RESULT. No way to get progress updates for long-running tasks.

### Design

**New endpoint:** `POST /ldp/stream` — accepts TASK_SUBMIT envelope, returns SSE stream.

**SSE event format:**

```
event: task_update
data: {"type": "TASK_UPDATE", "task_id": "...", "progress": 0.3, "message": "Analyzing..."}

event: task_update
data: {"type": "TASK_UPDATE", "task_id": "...", "progress": 0.7, "message": "Synthesizing..."}

event: task_result
data: {"type": "TASK_RESULT", "task_id": "...", "output": {...}, "provenance": {...}}
```

**Server — new async handler pattern:**

```python
class MyDelegate(LdpDelegate):
    # Existing sync method still works
    async def handle_task(self, skill, input_data, task_id):
        return {"answer": "42"}, 0.95

    # Optional streaming variant — yields (progress, message) tuples
    # Final yield uses a 3-tuple: (progress, output, confidence)
    async def handle_task_stream(self, skill, input_data, task_id):
        yield (0.2, "Parsing input...")
        result = await self.do_work(input_data)
        yield (0.8, "Finalizing...")
        yield (1.0, result, 0.95)  # 3-tuple signals completion
```

Note: Python async generators cannot use `return value`, so the final result is signaled via a 3-tuple `(1.0, output, confidence)` where `progress == 1.0` and the tuple has 3 elements. The server detects this and emits a TASK_RESULT instead of a TASK_UPDATE.

If `handle_task_stream` is not overridden, the server wraps `handle_task` in a single-event stream. No breaking change.

**Client side:**

```python
async for update in client.submit_task_stream(url, skill="reasoning", input_data={...}):
    if update["type"] == "task_update":
        print(f"{update['progress']:.0%} - {update['message']}")
    elif update["type"] == "task_result":
        print(update["output"])
```

```rust
let stream = adapter.invoke_stream(url, task_request).await?;
while let Some(envelope) = stream.next().await {
    // handle updates
}
```

**Implementation:**

| Component | Location | Change |
|-----------|----------|--------|
| Rust server | `src/server.rs` | New `/ldp/stream` route, async-stream + tokio-stream |
| Rust client | `src/client.rs` | New `send_message_stream()` returning `Stream<Item = LdpEnvelope>` |
| Python delegate | `delegate.py` | New SSE route, Starlette `StreamingResponse` |
| Python client | `client.py` | New `submit_task_stream()` using httpx `aiter_lines()` |

**Auth & signing:** Bearer token checked on initial POST. Each SSE event is a full `LdpEnvelope` with its own unique `message_id` and `timestamp`. If signing is enabled, each event envelope is independently signed. The TASK_UPDATE signing payload includes `task_id`, `progress`, and `message` fields (extending the current signing function which only includes `task_id`). Replay guard checks the initial TASK_SUBMIT only (SSE events are server-originated and flow one-way).

**Timeouts:** Keepalive ping every 15s (`:ping\n\n`). Client disconnection triggers server-side task cancellation.

---

## 5. Session TTL Expiration

### Problem

TTL is checked passively at `get_or_establish`. Expired sessions stay in memory forever. Server never actively reaps them.

### Design

**Background reaper:**

```
Every 60 seconds (configurable: reaper_interval_secs):
  1. Scan all sessions
  2. Skip sessions with in_flight_tasks > 0
  3. Close any where now() - last_used > ttl_secs
  4. Send best-effort SESSION_CLOSE to peer
  5. Remove from session map
  6. Log: "Reaped session {session_id} (idle {elapsed}s, ttl {ttl}s)"
```

**In-flight task tracking:** Add `in_flight_tasks: AtomicU32` (Rust) / `int` (Python) to `LdpSession`. Incremented on TASK_SUBMIT, decremented on TASK_RESULT/TASK_FAILED/TASK_CANCEL. The reaper skips sessions with active tasks to avoid mid-execution disruption.

**Implementation:**

| Component | Location | Change |
|-----------|----------|--------|
| Rust SessionManager | `src/session_manager.rs` | `start_reaper()` via tokio::spawn + CancellationToken |
| Python delegate | `delegate.py` | asyncio.create_task reaper on `run()` |
| Python client | `client.py` | Reaper on `__aenter__`, cancel on `__aexit__` |

**Server-side enforcement:**

```
On TASK_SUBMIT received:
  -> Session not found? TASK_FAILED with SESSION_NOT_FOUND
  -> Session expired? Send SESSION_CLOSE, return TASK_FAILED with SESSION_EXPIRED
```

New error codes added to `LdpError`:
- `SESSION_NOT_FOUND` (FailureCategory: Session)
- `SESSION_EXPIRED` (FailureCategory: Session)
- `REPLAY_DETECTED` (FailureCategory: Security — new category)

**Client-side recovery:**

When client receives `SESSION_EXPIRED`:
1. Remove cached session
2. Re-establish session automatically
3. Retry task submission (once)

**Tests:**

- Session expires after TTL -> reaper removes it
- Task submit on expired session -> SESSION_EXPIRED error
- Client auto-recovers from SESSION_EXPIRED
- Reaper sends SESSION_CLOSE to peer
- Active sessions (recently used) survive reaping

---

## 6. Trust Domain Rules #2-3

### Problem

Rule #1 works (same-domain implicit trust). Rules #2-3 have types (`allow_cross_domain`, `trusted_peers`) but the protocol handshake doesn't fully enforce mutual trust or exchange domain info.

### Design

**Rule #2 — Cross-domain with explicit peers (already works in `trusts()`):**

```
During SESSION_PROPOSE:
  Client sends: { trust_domain: "finance.acme.com" }
  Server checks: server.trust_domain.trusts("finance.acme.com")
```

**Rule #3 — Mutual trust verification (new):**

```
After server accepts:
  SESSION_ACCEPT includes: { trust_domain: "research.acme.com" }
  Client checks: client.trust_domain.trusts("research.acme.com")
  Fails? Client sends SESSION_CLOSE with TRUST_DOMAIN_MISMATCH
```

**Protocol changes:**

The client already sends `trust_domain` inside SESSION_PROPOSE's config object (current behavior in both Rust `session_manager.rs` and Python `client.py`). This stays unchanged. The only protocol addition:

| Message | Change |
|---------|--------|
| SESSION_ACCEPT | Add `trust_domain: String` field (server declares its domain for mutual verification) |

Note: trust_domain is NOT added to HELLO. The current flow where trust is validated during SESSION_PROPOSE is preserved. HELLO remains `{delegate_id, supported_modes}` per the RFC.

**Wildcard domains (new):**

Support single-level wildcard trust matching, following TLS certificate conventions: `*.acme.com` matches `finance.acme.com` but NOT `a.b.acme.com` (no multi-level).

```python
def trusts(self, peer: str) -> bool:
    if self.name == peer:
        return True
    if self.allow_cross_domain:
        for trusted in self.trusted_peers:
            if trusted.startswith("*."):
                suffix = trusted[1:]  # e.g., ".acme.com"
                if peer.endswith(suffix) and "." not in peer[:-len(suffix)]:
                    return True  # single-level only
            elif trusted == peer:
                return True
    return False
```

**Implementation:**

| Component | Location | Change |
|-----------|----------|--------|
| Rust messages | `src/types/messages.rs` | Add trust_domain to SessionAccept |
| Rust trust | `src/types/trust.rs` | Single-level wildcard matching in `trusts()` |
| Rust session_manager | `src/session_manager.rs` | Validate server's trust_domain from SESSION_ACCEPT |
| Rust server | `src/server.rs` | Include trust_domain in SESSION_ACCEPT response |
| Python messages | `types/messages.py` | Add trust_domain to SessionAccept |
| Python trust | `types/trust.py` | Single-level wildcard matching |
| Python client | `client.py` | Mutual validation after receiving SESSION_ACCEPT |
| Python delegate | `delegate.py` | Include trust_domain in SESSION_ACCEPT response |

**Backward compatibility:** SESSION_ACCEPT without trust_domain (from v0.2.0 servers) is treated as `"default"` domain by the client. No changes to HELLO or SESSION_PROPOSE.

**Tests:**

- Mutual trust: both sides configured -> session established
- One-sided trust: server trusts client but not reverse -> client closes session
- Wildcard: `*.acme.com` trusts `finance.acme.com` but not `evil.com`
- Wildcard single-level: `*.acme.com` does NOT match `a.b.acme.com`
- SERVER_ACCEPT carries trust_domain -> client validates
- Backward compat: SESSION_ACCEPT without trust_domain treated as "default"

---

## 7. Conformance Test Suite

### Installation

```bash
pip install ldp-protocol[conformance]
```

### CLI Usage

```bash
ldp-conformance http://localhost:8090
ldp-conformance http://localhost:8090 --verbose
ldp-conformance http://localhost:8090 --format json
ldp-conformance http://localhost:8090 --bearer-token sk-ldp-...
ldp-conformance http://localhost:8090 --signing-secret mysecret
ldp-conformance http://localhost:8090 --only identity,sessions
ldp-conformance http://localhost:8090 --timeout 30
```

### Test Categories

**REQUIRED (must pass for conformance):**

| Category | Checks |
|----------|--------|
| identity | Valid identity card at `/ldp/identity` and `/.well-known/ldp-identity`, all required fields, at least one capability |
| sessions | HELLO -> CAPABILITY_MANIFEST handshake, SESSION_PROPOSE -> SESSION_ACCEPT, SESSION_CLOSE, payload mode negotiation with fallback |
| tasks | TASK_SUBMIT -> TASK_RESULT within session, TASK_CANCEL acknowledged, TASK_FAILED on invalid skill, provenance present on every result |
| provenance | produced_by matches delegate_id, model_version present, verification_status valid enum, payload_mode_used matches negotiated |
| trust | Mismatched domain -> SESSION_REJECT, same domain -> SESSION_ACCEPT |

**OPTIONAL (reported, don't block conformance):**

| Category | Checks |
|----------|--------|
| signing | Signed messages accepted, tampered signature rejected, replay detection (duplicate nonce rejected) |
| streaming | POST /ldp/stream returns SSE, TASK_UPDATE events have progress, final event is TASK_RESULT or TASK_FAILED |
| bearer_auth | Missing token -> 401, invalid token -> 403 |
| session_ttl | Expired session returns SESSION_EXPIRED, reaper sends SESSION_CLOSE |
| contracts | Contract passed to provenance, FailClosed enforced on violation |

### Sample Output

```
LDP Conformance Test - http://localhost:8090
Target: My Agent (claude-sonnet-4-6)

  identity
    + Identity card valid
    + Well-known discovery
    + Required fields present
    + Capabilities declared

  sessions
    + Handshake lifecycle
    + Payload mode negotiation
    + Session close
    + Session expiration enforced

  tasks
    + Task submit and result
    + Task cancel
    + Invalid skill fails gracefully
    + Provenance present

  provenance
    + Produced_by matches delegate
    + Model version present
    + Verification status valid
    + Payload mode matches

  trust
    + Domain mismatch rejected
    + Same domain accepted

  signing (optional)
    + Signed messages accepted
    + Tampered rejected
    + Replay detection

  streaming (optional)
    - Not tested (endpoint not found)

Result: 16/16 required, 3/4 optional
Status: CONFORMANT
```

### Implementation

| Component | Location | Purpose |
|-----------|----------|---------|
| CLI entry | `conformance/cli.py` | Click-based CLI, parses args, runs checks |
| Runner | `conformance/runner.py` | Orchestrates check categories, collects results |
| Checks | `conformance/checks/` | One file per category (identity.py, sessions.py, etc.) |
| Report | `conformance/report.py` | Formats output (text, JSON) using rich |
| Entry point | `pyproject.toml` | `[project.scripts] ldp-conformance = "ldp_protocol.conformance.cli:main"` |
| Optional deps | `pyproject.toml` | `conformance = ["click>=8.0", "rich>=13.0"]` |

Each check is a standalone async function returning `Pass`, `Fail(reason)`, or `Skip(reason)`.

---

## 8. Ecosystem Artifacts

### CHANGELOG.md

Follows [Keep a Changelog](https://keepachangelog.com/). Retroactive entries for v0.1.0 and v0.2.0. Maintained with every PR going forward.

### OpenAPI Spec (docs/openapi.yaml)

Documents all HTTP endpoints:

| Path | Method | Description |
|------|--------|-------------|
| `/.well-known/ldp-identity` | GET | Identity card |
| `/ldp/identity` | GET | Identity card |
| `/ldp/capabilities` | GET | Capability manifest |
| `/ldp/messages` | POST | Send/receive LDP messages |
| `/ldp/stream` | POST | SSE streaming for task updates |

All schema types derived from Pydantic models. CI check validates OpenAPI spec against actual schemas to prevent drift.

Security schemes: `bearerAuth` (type: http, scheme: bearer).

### crates.io Publication

- `cargo publish --dry-run` added to CI
- Actual publish in release workflow
- Version sync check: CI fails if Cargo.toml and pyproject.toml versions diverge

### GitHub Release

On tag push, release workflow:
1. Extracts `[Unreleased]` section from CHANGELOG.md
2. Creates GitHub Release with that content
3. Publishes to PyPI + crates.io

### Blog Post

Written manually after release on sunilprakash.com. Covers what's new in v0.3.0, conformance suite announcement, OpenAPI spec, and call to action for contributors.

---

## Version

This release becomes **v0.3.0** (current: v0.2.0 on PyPI, v0.1.0 in Cargo.toml).

Both Cargo.toml and pyproject.toml bump to 0.3.0. RFC.md version stays at v0.1 (spec version is independent of implementation version).
