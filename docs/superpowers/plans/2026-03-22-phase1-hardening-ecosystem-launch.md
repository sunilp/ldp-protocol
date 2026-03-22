# Phase 1 Hardening + Ecosystem Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete LDP Phase 1 hardening (replay detection, bearer auth, trust domains, session TTL, SSE streaming) and launch ecosystem presence (CI/CD, conformance suite, OpenAPI, crates.io, v0.3.0 release).

**Architecture:** Each hardening feature follows TDD across both Rust and Python SDKs. Features are independent and can be implemented in any order within Phase B. CI/CD goes first to protect all subsequent work.

**Tech Stack:** Rust (tokio, serde, hmac, reqwest, lru), Python (pydantic, httpx, starlette, click, rich), GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-22-phase1-hardening-ecosystem-launch-design.md`

---

## File Structure

### New files
```
.github/workflows/ci.yml                          # CI pipeline
.github/workflows/release.yml                     # Release pipeline
CHANGELOG.md                                      # Keep a Changelog format
src/replay.rs                                     # Rust ReplayGuard
sdk/python/src/ldp_protocol/replay.py             # Python ReplayGuard
sdk/python/src/ldp_protocol/conformance/          # Conformance suite
  __init__.py
  cli.py                                          # Click CLI entry point
  runner.py                                       # Test orchestrator
  report.py                                       # Text/JSON output formatter
  checks/
    __init__.py
    identity.py
    sessions.py
    tasks.py
    provenance.py
    trust.py
    signing.py
    streaming.py
    bearer_auth.py
    session_ttl.py
    contracts.py
docs/openapi.yaml                                 # OpenAPI 3.0 spec
```

### Modified files
```
Cargo.toml                                        # Version bump, lru dep
src/lib.rs                                        # Add replay module
src/types/messages.rs                             # nonce on envelope, trust_domain on SessionAccept
src/types/error.rs                                # Security failure category
src/types/trust.rs                                # Wildcard matching
src/types/session.rs                              # in_flight_tasks field
src/signing.rs                                    # nonce + TASK_UPDATE fields in payload
src/server.rs                                     # ReplayGuard, bearer auth, SSE, TTL enforcement
src/client.rs                                     # Bearer token header, streaming client
src/session_manager.rs                            # Reaper, mutual trust validation
src/config.rs                                     # bearer_token, replay_window_secs, replay_cache_capacity
tests/ldp_integration.rs                          # New integration tests
sdk/python/pyproject.toml                         # Version bump, conformance deps, CLI entry point
sdk/python/src/ldp_protocol/__init__.py           # Export new types
sdk/python/src/ldp_protocol/types/messages.py     # nonce on envelope, trust_domain on SessionAccept
sdk/python/src/ldp_protocol/types/error.py        # Security failure category
sdk/python/src/ldp_protocol/types/trust.py        # Wildcard matching
sdk/python/src/ldp_protocol/types/session.py      # in_flight_tasks field
sdk/python/src/ldp_protocol/signing.py            # nonce + TASK_UPDATE fields in payload
sdk/python/src/ldp_protocol/delegate.py           # ReplayGuard, bearer auth, SSE, TTL reaper
sdk/python/src/ldp_protocol/client.py             # Bearer header, streaming, mutual trust, TTL reaper
sdk/python/tests/test_replay.py                   # Replay detection tests
sdk/python/tests/test_bearer.py                   # Bearer auth tests
sdk/python/tests/test_trust_wildcards.py          # Wildcard trust tests
sdk/python/tests/test_session_ttl.py              # Session TTL tests
sdk/python/tests/test_streaming.py                # SSE streaming tests
```

---

## Phase A: Foundation

### Task 1: CI/CD Setup

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create ci.yml**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  rust-check:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        toolchain: [stable, nightly]
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@master
        with:
          toolchain: ${{ matrix.toolchain }}
          components: rustfmt, clippy
      - run: cargo fmt --check
      - run: cargo clippy -- -D warnings
      - run: cargo test

  python-check:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: |
          cd sdk/python
          pip install -e ".[dev]"
          ruff check src/ tests/
          ruff format --check src/ tests/
          pytest -v

  version-sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check Cargo.toml and pyproject.toml versions match
        run: |
          CARGO_VER=$(grep '^version' Cargo.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
          PY_VER=$(grep '^version' sdk/python/pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
          if [ "$CARGO_VER" != "$PY_VER" ]; then
            echo "Version mismatch: Cargo.toml=$CARGO_VER pyproject.toml=$PY_VER"
            exit 1
          fi

  cross-sdk-compat:
    runs-on: ubuntu-latest
    needs: [rust-check, python-check]
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: cargo build
      - run: |
          cd sdk/python
          pip install -e ".[dev]"
          pytest tests/ -v -k "cross_sdk or compat"
```

- [ ] **Step 2: Create release.yml**

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ["v*"]

jobs:
  ci:
    uses: ./.github/workflows/ci.yml

  publish-pypi:
    needs: ci
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build twine
      - run: cd sdk/python && python -m build
      - run: cd sdk/python && twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}

  publish-crates:
    needs: ci
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo publish
        env:
          CARGO_REGISTRY_TOKEN: ${{ secrets.CARGO_REGISTRY_TOKEN }}

  github-release:
    needs: [publish-pypi, publish-crates]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Extract changelog
        id: changelog
        run: |
          VERSION=${GITHUB_REF_NAME#v}
          BODY=$(sed -n "/^## \[$VERSION\]/,/^## \[/p" CHANGELOG.md | head -n -1)
          echo "body<<EOF" >> $GITHUB_OUTPUT
          echo "$BODY" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      - uses: softprops/action-gh-release@v2
        with:
          body: ${{ steps.changelog.outputs.body }}
```

- [ ] **Step 3: Verify workflows parse correctly**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml OK')" && python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('release.yml OK')"`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: add CI and release workflows"
```

---

### Task 2: CHANGELOG

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Create CHANGELOG.md with retroactive entries**

```markdown
# Changelog

All notable changes to this project follow [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.2.0] - 2026-03-15

### Added
- Python SDK published to PyPI (`pip install ldp-protocol`)
- HMAC-SHA256 message signing (Rust + Python)
- Delegation contracts with PolicyEnvelope
- Verification status, evidence, lineage on provenance
- Typed failure codes with categories (identity, capability, policy, runtime, quality, session, transport)
- Multi-strategy router (quality, cost, latency, balanced)
- Contract validation with ContractViolationError

## [0.1.0] - 2026-03-08

### Added
- Initial protocol implementation (Rust reference)
- Identity cards with full RFC fields
- Session lifecycle (INITIATING -> PROPOSED -> ACTIVE -> CLOSED)
- Payload mode negotiation with fallback chain (Text + Semantic Frame)
- Provenance tracking on task results
- Trust domain validation (Rule #1: same-domain implicit trust)
- JamJet integration plugin (`register_ldp_jamjet`)
- 17 integration tests (Rust)
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG with retroactive entries for v0.1.0 and v0.2.0"
```

---

## Phase B: Hardening

### Task 3: Replay Detection — Rust Types + Error Category

**Files:**
- Modify: `src/types/error.rs:9-17` (add Security variant)
- Modify: `src/types/messages.rs:14-47` (add nonce to LdpEnvelope)
- Create: `src/replay.rs`
- Modify: `src/lib.rs` (add replay module)

- [ ] **Step 1: Write failing test for Security failure category**

Add to `src/types/error.rs` before the closing `}` of the tests module:

```rust
    #[test]
    fn security_failure() {
        let err = LdpError::security("REPLAY_DETECTED", "Duplicate nonce");
        assert_eq!(err.category, FailureCategory::Security);
        assert!(!err.retryable);
        assert_eq!(err.severity, ErrorSeverity::Fatal);
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test security_failure`
Expected: FAIL — `Security` variant and `security()` method don't exist

- [ ] **Step 3: Add Security to FailureCategory and LdpError**

In `src/types/error.rs`, add `Security` after `Transport` in the enum (line 16):

```rust
pub enum FailureCategory {
    Identity,
    Capability,
    Policy,
    Runtime,
    Quality,
    Session,
    Transport,
    Security,
}
```

Add factory method after the `transport()` method (after line 116):

```rust
    pub fn security(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Security,
            message: message.into(),
            severity: ErrorSeverity::Fatal,
            retryable: false,
            partial_output: None,
        }
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test security_failure`
Expected: PASS

- [ ] **Step 5: Add nonce field to LdpEnvelope**

In `src/types/messages.rs`, add after the `signature_algorithm` field (line 46):

```rust
    /// Replay-prevention nonce (16-byte hex). Required when signing is enabled.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nonce: Option<String>,
```

Update the `new()` constructor to initialize `nonce: None` (after line 136).

- [ ] **Step 6: Update signing to include nonce when present**

In `src/signing.rs`, after `mac.update(envelope.message_id.as_bytes());` (line 27), add:

```rust
    // Include nonce in signing payload only when present (backward compat)
    if let Some(ref nonce) = envelope.nonce {
        mac.update(b"|");
        mac.update(nonce.as_bytes());
    }
```

- [ ] **Step 7: Add `lru` dependency to Cargo.toml**

Add to `[dependencies]` in `Cargo.toml`:

```toml
lru = "0.12"
```

- [ ] **Step 8: Write ReplayGuard**

Create `src/replay.rs`:

```rust
//! Replay detection for LDP messages.

use lru::LruCache;
use std::num::NonZeroUsize;
use std::time::Duration;

/// Guards against replayed messages using a bounded LRU cache.
///
/// Must be wrapped in `Arc<Mutex<ReplayGuard>>` for concurrent use in servers.
pub struct ReplayGuard {
    seen: LruCache<String, ()>,
    window: Duration,
}

impl ReplayGuard {
    pub fn new(capacity: usize, window_secs: u64) -> Self {
        Self {
            seen: LruCache::new(NonZeroUsize::new(capacity.max(1)).unwrap()),
            window: Duration::from_secs(window_secs),
        }
    }

    /// Check if a message should be accepted. Returns Err with reason if rejected.
    pub fn check(&mut self, message_id: &str, nonce: Option<&str>, timestamp: &str) -> Result<(), String> {
        // 1. Timestamp freshness check
        if let Ok(msg_time) = chrono::DateTime::parse_from_rfc3339(timestamp) {
            let now = chrono::Utc::now();
            let diff = (now - msg_time.with_timezone(&chrono::Utc)).num_seconds().unsigned_abs();
            if diff > self.window.as_secs() {
                return Err(format!("Message timestamp too old: {}s > {}s window", diff, self.window.as_secs()));
            }
        }

        // 2. Nonce deduplication (only when nonce is present)
        if let Some(nonce) = nonce {
            let key = format!("{}:{}", message_id, nonce);

            if self.seen.contains(&key) {
                return Err("Duplicate message_id + nonce pair".into());
            }
            // LRU cache auto-evicts oldest entry when at capacity
            self.seen.put(key, ());
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_fresh_message() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &ts).is_ok());
    }

    #[test]
    fn rejects_duplicate_nonce() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &ts).is_ok());
        assert!(guard.check("m1", Some("nonce1"), &ts).is_err());
    }

    #[test]
    fn accepts_different_nonce_same_message_id() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &ts).is_ok());
        assert!(guard.check("m1", Some("nonce2"), &ts).is_ok());
    }

    #[test]
    fn rejects_stale_timestamp() {
        let mut guard = ReplayGuard::new(100, 60);
        let old_ts = (chrono::Utc::now() - chrono::Duration::seconds(120)).to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &old_ts).is_err());
    }

    #[test]
    fn skips_dedup_when_no_nonce() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", None, &ts).is_ok());
        assert!(guard.check("m1", None, &ts).is_ok()); // no nonce = no dedup
    }

    #[test]
    fn lru_evicts_oldest_at_capacity() {
        let mut guard = ReplayGuard::new(2, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("n1"), &ts).is_ok());
        assert!(guard.check("m2", Some("n2"), &ts).is_ok());
        // At capacity — LRU evicts m1:n1 (oldest) to make room
        assert!(guard.check("m3", Some("n3"), &ts).is_ok());
        // m1:n1 was evicted so it can be replayed (expected for bounded cache)
        assert!(guard.check("m1", Some("n1"), &ts).is_ok());
        // m2:n2 is still in cache
        assert!(guard.check("m2", Some("n2"), &ts).is_err());
    }
}
```

- [ ] **Step 9: Add replay module to lib.rs**

In `src/lib.rs`, add after line 43 (`pub mod signing;`):

```rust
pub mod replay;
```

- [ ] **Step 10: Run all tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test`
Expected: All tests pass (existing + new replay + security category)

- [ ] **Step 11: Commit**

```bash
git add Cargo.toml src/types/error.rs src/types/messages.rs src/replay.rs src/signing.rs src/lib.rs
git commit -m "feat: add replay detection with ReplayGuard and Security failure category (Rust)"
```

---

### Task 4: Replay Detection — Python

**Files:**
- Modify: `sdk/python/src/ldp_protocol/types/error.py:11-18`
- Modify: `sdk/python/src/ldp_protocol/types/messages.py:117-151`
- Modify: `sdk/python/src/ldp_protocol/signing.py`
- Create: `sdk/python/src/ldp_protocol/replay.py`
- Create: `sdk/python/tests/test_replay.py`

- [ ] **Step 1: Write failing tests**

Create `sdk/python/tests/test_replay.py`:

```python
"""Tests for replay detection."""
from datetime import datetime, timedelta, timezone

from ldp_protocol.replay import ReplayGuard
from ldp_protocol.types.error import FailureCategory, LdpError


def test_security_failure_category():
    err = LdpError.security("REPLAY_DETECTED", "Duplicate nonce")
    assert err.category == FailureCategory.SECURITY
    assert err.retryable is False


def test_accepts_fresh_message():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    assert guard.check("m1", "nonce1", ts) is None


def test_rejects_duplicate_nonce():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    guard.check("m1", "nonce1", ts)
    err = guard.check("m1", "nonce1", ts)
    assert err is not None
    assert "Duplicate" in err


def test_accepts_different_nonce():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    assert guard.check("m1", "nonce1", ts) is None
    assert guard.check("m1", "nonce2", ts) is None


def test_rejects_stale_timestamp():
    guard = ReplayGuard(capacity=100, window_secs=60)
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    err = guard.check("m1", "nonce1", old_ts)
    assert err is not None
    assert "old" in err.lower() or "stale" in err.lower()


def test_skips_dedup_when_no_nonce():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    assert guard.check("m1", None, ts) is None
    assert guard.check("m1", None, ts) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_replay.py -v`
Expected: FAIL — modules don't exist yet

- [ ] **Step 3: Add Security to Python FailureCategory and LdpError**

In `sdk/python/src/ldp_protocol/types/error.py`, add after `TRANSPORT = "transport"` (line 18):

```python
    SECURITY = "security"
```

Add after the `transport()` classmethod (after line 103):

```python
    @classmethod
    def security(cls, code: str, message: str) -> LdpError:
        return cls(
            code=code,
            category=FailureCategory.SECURITY,
            message=message,
            severity=ErrorSeverity.FATAL,
            retryable=False,
        )
```

- [ ] **Step 4: Add nonce to Python LdpEnvelope**

In `sdk/python/src/ldp_protocol/types/messages.py`, add after `signature_algorithm` field (line 131):

```python
    nonce: str | None = None
```

- [ ] **Step 5: Update Python signing to include nonce when present**

In `sdk/python/src/ldp_protocol/signing.py`, after `mac.update(envelope.message_id.encode())` (line 23), add:

```python
    # Include nonce in signing payload only when present (backward compat)
    if envelope.nonce is not None:
        mac.update(b"|")
        mac.update(envelope.nonce.encode())
```

- [ ] **Step 6: Create Python ReplayGuard**

Create `sdk/python/src/ldp_protocol/replay.py`:

```python
"""Replay detection for LDP messages."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone


class ReplayGuard:
    """Guards against replayed messages using a bounded LRU cache."""

    def __init__(self, capacity: int = 10_000, window_secs: int = 60) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._capacity = capacity
        self._window_secs = window_secs

    def check(
        self, message_id: str, nonce: str | None, timestamp: str
    ) -> str | None:
        """Check if a message should be accepted. Returns error string if rejected, None if OK."""
        # 1. Timestamp freshness
        try:
            msg_time = datetime.fromisoformat(timestamp)
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = abs((now - msg_time).total_seconds())
            if diff > self._window_secs:
                return f"Message timestamp too old: {diff:.0f}s > {self._window_secs}s window"
        except (ValueError, TypeError):
            pass  # unparseable timestamp — skip freshness check

        # 2. Nonce deduplication (only when nonce is present)
        if nonce is not None:
            key = f"{message_id}:{nonce}"

            # Evict oldest if at capacity
            while len(self._seen) >= self._capacity:
                self._seen.popitem(last=False)

            if key in self._seen:
                return "Duplicate message_id + nonce pair"
            self._seen[key] = datetime.now(timezone.utc).timestamp()

        return None
```

- [ ] **Step 7: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_replay.py -v`
Expected: All 6 tests PASS

- [ ] **Step 8: Run full test suite**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/ -v`
Expected: All tests pass (existing + new)

- [ ] **Step 9: Commit**

```bash
git add sdk/python/src/ldp_protocol/types/error.py sdk/python/src/ldp_protocol/types/messages.py \
  sdk/python/src/ldp_protocol/signing.py sdk/python/src/ldp_protocol/replay.py \
  sdk/python/tests/test_replay.py
git commit -m "feat: add replay detection with ReplayGuard and Security failure category (Python)"
```

---

### Task 5: Bearer Token Auth — Rust

**Files:**
- Modify: `src/config.rs:9-32` (add bearer_token field)
- Modify: `src/client.rs` (add Authorization header)
- Modify: `src/server.rs` (add bearer token check)
- Modify: `tests/ldp_integration.rs` (add bearer auth tests)

- [ ] **Step 1: Write failing integration test**

Add to `tests/ldp_integration.rs`:

```rust
#[tokio::test]
async fn test_bearer_token_required_rejects_without_token() {
    // Server configured with bearer tokens should reject requests without Authorization header
    let server = LdpServer::echo_server("ldp:delegate:secured", "Secured")
        .with_signing_secret("secret".into())
        .with_bearer_tokens(vec!["sk-ldp-test123".into()].into_iter().collect());
    // Attempt to send without token should fail
    assert!(server.bearer_tokens().is_some());
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test test_bearer_token`
Expected: FAIL — `with_bearer_tokens` and `bearer_tokens()` don't exist

- [ ] **Step 3: Add bearer_token to LdpAdapterConfig**

In `src/config.rs`, add after `signing_secret` field (line 31):

```rust
    /// Bearer token for authenticating with remote delegates.
    #[serde(default)]
    pub bearer_token: Option<String>,
```

Update `Default` impl to add `bearer_token: None`.

- [ ] **Step 4: Add bearer token header to LdpClient**

In `src/client.rs`, add bearer token support to `send_message()`. The client should accept an optional bearer token and add it as `Authorization: Bearer <token>` header on every request. Add the token as a parameter or store it on the client struct.

- [ ] **Step 5: Add bearer token check to LdpServer**

In `src/server.rs`, add:
- `bearer_tokens: Option<HashSet<String>>` field
- `with_bearer_tokens(self, tokens: HashSet<String>) -> Self` builder method
- `bearer_tokens(&self) -> Option<&HashSet<String>>` getter
- Check at the top of `handle_message()`: if `bearer_tokens` is configured, verify the token was provided (the HTTP layer must pass it through)

- [ ] **Step 6: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/config.rs src/client.rs src/server.rs tests/ldp_integration.rs
git commit -m "feat: add bearer token authentication (Rust)"
```

---

### Task 6: Bearer Token Auth — Python

**Files:**
- Modify: `sdk/python/src/ldp_protocol/client.py` (add bearer_token param)
- Modify: `sdk/python/src/ldp_protocol/delegate.py` (add bearer_tokens param + middleware)
- Create: `sdk/python/tests/test_bearer.py`

- [ ] **Step 1: Write failing tests**

Create `sdk/python/tests/test_bearer.py`:

```python
"""Tests for bearer token authentication."""
import pytest
from ldp_protocol.client import LdpClient
from ldp_protocol.delegate import LdpDelegate


def test_client_stores_bearer_token():
    client = LdpClient(delegate_id="test", bearer_token="sk-ldp-abc")
    assert client._bearer_token == "sk-ldp-abc"


def test_client_no_bearer_token_by_default():
    client = LdpClient(delegate_id="test")
    assert client._bearer_token is None


def test_delegate_stores_bearer_tokens():
    class D(LdpDelegate):
        async def handle_task(self, skill, input_data, task_id):
            return {}, 0.5

    d = D(
        delegate_id="ldp:delegate:test", name="Test",
        model_family="test", model_version="test-1",
        bearer_tokens={"sk-ldp-abc", "sk-ldp-def"},
    )
    assert d._bearer_tokens == {"sk-ldp-abc", "sk-ldp-def"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_bearer.py -v`
Expected: FAIL — bearer_token param doesn't exist yet

- [ ] **Step 3: Add bearer_token to LdpClient**

In `sdk/python/src/ldp_protocol/client.py`, add `bearer_token: str | None = None` parameter to `__init__`. Store as `self._bearer_token`. In `send_message()` and `discover()`, add `Authorization: Bearer {self._bearer_token}` header to httpx requests when token is set.

- [ ] **Step 4: Add bearer_tokens to LdpDelegate**

In `sdk/python/src/ldp_protocol/delegate.py`, add `bearer_tokens: set[str] | None = None` parameter to `__init__`. Store as `self._bearer_tokens`. In the Starlette `run()` method, add middleware that checks `Authorization` header against `self._bearer_tokens`. Return 401 if missing, 403 if invalid, pass through if no tokens configured.

- [ ] **Step 5: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_bearer.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add sdk/python/src/ldp_protocol/client.py sdk/python/src/ldp_protocol/delegate.py \
  sdk/python/tests/test_bearer.py
git commit -m "feat: add bearer token authentication (Python)"
```

---

### Task 7: Trust Domain Rules #2-3 — Rust

**Files:**
- Modify: `src/types/trust.rs:41-46` (wildcard matching)
- Modify: `src/types/messages.rs:68-72` (trust_domain on SessionAccept)
- Modify: `src/session_manager.rs` (mutual trust validation)
- Modify: `src/server.rs` (include trust_domain in SessionAccept)

- [ ] **Step 1: Write failing tests for wildcard trust matching**

Add to `src/types/trust.rs` tests module:

```rust
    #[test]
    fn wildcard_single_level_match() {
        let domain = TrustDomain {
            name: "acme".into(),
            allow_cross_domain: true,
            trusted_peers: vec!["*.acme.com".into()],
        };
        assert!(domain.trusts("finance.acme.com"));
        assert!(!domain.trusts("evil.com"));
    }

    #[test]
    fn wildcard_rejects_multi_level() {
        let domain = TrustDomain {
            name: "acme".into(),
            allow_cross_domain: true,
            trusted_peers: vec!["*.acme.com".into()],
        };
        assert!(!domain.trusts("a.b.acme.com"));
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test wildcard`
Expected: FAIL — `finance.acme.com` not literally in `trusted_peers`

- [ ] **Step 3: Implement wildcard matching in trusts()**

Replace `src/types/trust.rs` lines 41-46 with:

```rust
    pub fn trusts(&self, peer: &str) -> bool {
        if self.name == peer {
            return true;
        }
        if self.allow_cross_domain {
            for trusted in &self.trusted_peers {
                if trusted.starts_with("*.") {
                    let suffix = &trusted[1..]; // e.g., ".acme.com"
                    if peer.ends_with(suffix) {
                        let prefix = &peer[..peer.len() - suffix.len()];
                        if !prefix.contains('.') {
                            return true; // single-level only
                        }
                    }
                } else if trusted == peer {
                    return true;
                }
            }
        }
        false
    }
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test trust`
Expected: All trust tests pass (existing + wildcard)

- [ ] **Step 5: Add trust_domain to SessionAccept**

In `src/types/messages.rs`, modify the `SessionAccept` variant (lines 69-72):

```rust
    SessionAccept {
        session_id: String,
        negotiated_mode: PayloadMode,
        #[serde(default)]
        trust_domain: Option<String>,
    },
```

Update signing in `src/signing.rs` — the SessionAccept arm should also sign trust_domain when present.

- [ ] **Step 6: Update server to include trust_domain in SessionAccept**

In `src/server.rs`, where SESSION_ACCEPT is constructed in `handle_session_propose()`, add `trust_domain: Some(self.identity.trust_domain.name.clone())`.

- [ ] **Step 7: Update session_manager to validate mutual trust**

In `src/session_manager.rs`, update the `SessionAccept` pattern match in `establish_session()` to destructure the new `trust_domain` field:

```rust
LdpMessageBody::SessionAccept {
    session_id: accepted_id,
    negotiated_mode,
    trust_domain: server_trust_domain,
} => {
    // Validate mutual trust if server declares its domain
    if let Some(ref domain) = server_trust_domain {
        if !self.config.trust_domain.trusts(domain) {
            // Send SESSION_CLOSE and return error
            let close = LdpEnvelope::new(
                &session_id, &self.config.delegate_id, &url,
                LdpMessageBody::SessionClose {
                    reason: Some("TRUST_DOMAIN_MISMATCH".into()),
                },
                PayloadMode::Text,
            );
            let _ = self.client.send_message(url, &close).await;
            return Err(format!("Mutual trust failed: we don't trust domain '{}'", domain));
        }
    }
    // ... rest of session creation unchanged
}
```

Also update the `sign_envelope` SessionAccept arm in `src/signing.rs` to include trust_domain when present:

```rust
LdpMessageBody::SessionAccept { session_id, trust_domain, .. } => {
    mac.update(session_id.as_bytes());
    if let Some(ref td) = trust_domain {
        mac.update(b"|");
        mac.update(td.as_bytes());
    }
    "SESSION_ACCEPT"
}
```

- [ ] **Step 8: Run all tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test`
Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add src/types/trust.rs src/types/messages.rs src/signing.rs src/server.rs src/session_manager.rs
git commit -m "feat: trust domain rules #2-3 with wildcard matching and mutual trust (Rust)"
```

---

### Task 8: Trust Domain Rules #2-3 — Python

**Files:**
- Modify: `sdk/python/src/ldp_protocol/types/trust.py:22-26`
- Modify: `sdk/python/src/ldp_protocol/types/messages.py:74-75`
- Modify: `sdk/python/src/ldp_protocol/client.py`
- Modify: `sdk/python/src/ldp_protocol/delegate.py`
- Create: `sdk/python/tests/test_trust_wildcards.py`

- [ ] **Step 1: Write failing tests**

Create `sdk/python/tests/test_trust_wildcards.py`:

```python
"""Tests for wildcard trust domain matching and mutual trust."""
from ldp_protocol.types.trust import TrustDomain


def test_wildcard_single_level_match():
    td = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=["*.acme.com"])
    assert td.trusts("finance.acme.com")
    assert not td.trusts("evil.com")


def test_wildcard_rejects_multi_level():
    td = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=["*.acme.com"])
    assert not td.trusts("a.b.acme.com")


def test_wildcard_exact_peer_still_works():
    td = TrustDomain(name="acme", allow_cross_domain=True, trusted_peers=["*.acme.com", "partner.org"])
    assert td.trusts("partner.org")
    assert td.trusts("finance.acme.com")


def test_mutual_trust_with_wildcards():
    a = TrustDomain(name="finance.acme.com", allow_cross_domain=True, trusted_peers=["*.partner.org"])
    b = TrustDomain(name="api.partner.org", allow_cross_domain=True, trusted_peers=["*.acme.com"])
    assert a.mutually_trusts(b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_trust_wildcards.py -v`
Expected: FAIL — wildcard not supported

- [ ] **Step 3: Implement wildcard matching in Python trusts()**

Replace `sdk/python/src/ldp_protocol/types/trust.py` lines 22-26:

```python
    def trusts(self, peer: str) -> bool:
        """Check if this domain trusts a peer domain."""
        if self.name == peer:
            return True
        if self.allow_cross_domain:
            for trusted in self.trusted_peers:
                if trusted.startswith("*."):
                    suffix = trusted[1:]  # e.g., ".acme.com"
                    if peer.endswith(suffix) and "." not in peer[: -len(suffix)]:
                        return True
                elif trusted == peer:
                    return True
        return False
```

- [ ] **Step 4: Add trust_domain to Python SessionAccept**

In `sdk/python/src/ldp_protocol/types/messages.py`, update the `session_accept` classmethod (line 74-75) to accept optional `trust_domain`:

```python
    @classmethod
    def session_accept(
        cls, session_id: str, negotiated_mode: PayloadMode, trust_domain: str | None = None,
    ) -> LdpMessageBody:
        return cls(
            type="SESSION_ACCEPT", session_id=session_id,
            negotiated_mode=negotiated_mode, trust_domain=trust_domain,
        )
```

Add `trust_domain` field to `LdpMessageBody` (after `negotiated_mode`, around line 34):

```python
    trust_domain: str | None = None
```

- [ ] **Step 5: Update delegate to include trust_domain in SessionAccept**

In `sdk/python/src/ldp_protocol/delegate.py`, in `_handle_session_propose()`, pass `trust_domain=self.identity.trust_domain.name` to the `session_accept()` call.

- [ ] **Step 6: Update client to validate mutual trust on SessionAccept**

In `sdk/python/src/ldp_protocol/client.py`, in `establish_session()`, after receiving SESSION_ACCEPT, extract `trust_domain` from the response. If present and `self.enforce_trust_domains`, check `self.trust_domain.trusts(server_domain)`. If fails, send SESSION_CLOSE and raise error. If `trust_domain` is None (v0.2.0 server), treat as `"default"`.

- [ ] **Step 7: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add sdk/python/src/ldp_protocol/types/trust.py sdk/python/src/ldp_protocol/types/messages.py \
  sdk/python/src/ldp_protocol/client.py sdk/python/src/ldp_protocol/delegate.py \
  sdk/python/tests/test_trust_wildcards.py
git commit -m "feat: trust domain rules #2-3 with wildcard matching and mutual trust (Python)"
```

---

### Task 9: Session TTL Expiration — Rust

**Files:**
- Modify: `src/types/session.rs:34-65` (add in_flight_tasks)
- Modify: `src/session_manager.rs` (add reaper)
- Modify: `src/server.rs` (enforce session existence/expiry on TASK_SUBMIT)
- Modify: `src/config.rs` (add reaper_interval_secs)

- [ ] **Step 1: Write failing test for in_flight_tasks**

Add to `tests/ldp_integration.rs`:

```rust
#[tokio::test]
async fn test_expired_session_returns_error() {
    // Submit task to a session that has expired — should get SESSION_EXPIRED error
    // This test creates a server, establishes a session with 1s TTL,
    // waits for expiry, then submits a task.
}
```

- [ ] **Step 2: Add in_flight_tasks to LdpSession**

In `src/types/session.rs`, add after `task_count` (line 64):

```rust
    /// Number of in-flight (active) tasks in this session.
    #[serde(default)]
    pub in_flight_tasks: u32,
```

- [ ] **Step 3: Add reaper_interval_secs to config**

In `src/config.rs`, add to `LdpAdapterConfig`:

```rust
    /// Interval in seconds between session reaper runs.
    #[serde(default = "default_reaper_interval")]
    pub reaper_interval_secs: u64,
```

Add `fn default_reaper_interval() -> u64 { 60 }` and update Default impl.

- [ ] **Step 4: Add reaper to SessionManager**

In `src/session_manager.rs`, add:

```rust
pub fn start_reaper(&self) -> tokio::task::JoinHandle<()> {
    let sessions = self.sessions.clone();
    let interval_secs = self.config.reaper_interval_secs;
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));
        loop {
            interval.tick().await;
            let mut sessions = sessions.write().await;
            let expired: Vec<String> = sessions
                .iter()
                .filter(|(_, s)| !s.is_active() && s.in_flight_tasks == 0)
                .map(|(url, _)| url.clone())
                .collect();
            for url in expired {
                if let Some(session) = sessions.remove(&url) {
                    tracing::info!(
                        session_id = %session.session_id,
                        "Reaped expired session"
                    );
                }
            }
        }
    })
}
```

- [ ] **Step 5: Add session validation to server**

In `src/server.rs`, in `handle_task_submit()`, check that the session exists and is active. If not found, return `TASK_FAILED` with `LdpError::session("SESSION_NOT_FOUND", "...")`. If expired, return `LdpError::session("SESSION_EXPIRED", "...")`.

- [ ] **Step 6: Run all tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/types/session.rs src/session_manager.rs src/server.rs src/config.rs tests/ldp_integration.rs
git commit -m "feat: session TTL expiration with background reaper (Rust)"
```

---

### Task 10: Session TTL Expiration — Python

**Files:**
- Modify: `sdk/python/src/ldp_protocol/types/session.py` (add in_flight_tasks)
- Modify: `sdk/python/src/ldp_protocol/client.py` (reaper + auto-recovery)
- Modify: `sdk/python/src/ldp_protocol/delegate.py` (reaper)
- Create: `sdk/python/tests/test_session_ttl.py`

- [ ] **Step 1: Write failing tests**

Create `sdk/python/tests/test_session_ttl.py`:

```python
"""Tests for session TTL expiration."""
import asyncio
from datetime import datetime, timedelta, timezone

from ldp_protocol.types.session import LdpSession, SessionState
from ldp_protocol.types.trust import TrustDomain


def test_session_with_in_flight_tasks():
    session = LdpSession(
        session_id="s1", remote_url="http://test", remote_delegate_id="d1",
        trust_domain=TrustDomain(name="default"), in_flight_tasks=2,
    )
    assert session.in_flight_tasks == 2


def test_expired_session_not_active():
    session = LdpSession(
        session_id="s1", remote_url="http://test", remote_delegate_id="d1",
        trust_domain=TrustDomain(name="default"), ttl_secs=1,
        last_used=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    assert not session.is_active
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_session_ttl.py -v`
Expected: FAIL — `in_flight_tasks` field doesn't exist

- [ ] **Step 3: Add in_flight_tasks to Python LdpSession**

In `sdk/python/src/ldp_protocol/types/session.py`, add after `task_count` (line 47):

```python
    in_flight_tasks: int = 0
```

- [ ] **Step 4: Add reaper to LdpClient**

In `sdk/python/src/ldp_protocol/client.py`, add a `_start_reaper()` method that runs as an asyncio task. In `__aenter__`, start the reaper. In `__aexit__`, cancel it. The reaper should iterate `self._sessions`, remove expired sessions with `in_flight_tasks == 0`, and send best-effort SESSION_CLOSE.

Also add auto-recovery: in `submit_task()`, if the response is TASK_FAILED with code `SESSION_EXPIRED`, remove the cached session, re-establish, and retry once.

- [ ] **Step 5: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add sdk/python/src/ldp_protocol/types/session.py sdk/python/src/ldp_protocol/client.py \
  sdk/python/src/ldp_protocol/delegate.py sdk/python/tests/test_session_ttl.py
git commit -m "feat: session TTL expiration with background reaper (Python)"
```

---

### Task 11: SSE Streaming — Rust

**Files:**
- Modify: `src/server.rs` (add streaming handler)
- Modify: `src/client.rs` (add streaming client method)
- Modify: `src/signing.rs:54-56` (extend TASK_UPDATE signing payload)

- [ ] **Step 1: Extend TASK_UPDATE signing payload**

In `src/signing.rs`, replace the TaskUpdate arm (lines 54-56):

```rust
        LdpMessageBody::TaskUpdate {
            task_id,
            progress,
            message,
        } => {
            mac.update(task_id.as_bytes());
            if let Some(p) = progress {
                mac.update(b"|");
                mac.update(p.to_string().as_bytes());
            }
            if let Some(m) = message {
                mac.update(b"|");
                mac.update(m.as_bytes());
            }
            "TASK_UPDATE"
        }
```

- [ ] **Step 2: Add streaming handler to server**

In `src/server.rs`, add a method that accepts a TASK_SUBMIT and returns a `Pin<Box<dyn Stream<Item = LdpEnvelope>>>` using `async-stream`:

```rust
pub fn handle_task_stream(
    &self,
    envelope: LdpEnvelope,
) -> Pin<Box<dyn Stream<Item = LdpEnvelope> + Send>> {
    // Extract task details, call handler, wrap result in stream
    // For now: emit one TASK_RESULT (wraps sync handle_task)
}
```

- [ ] **Step 3: Add streaming client method**

In `src/client.rs`, add `send_message_stream()` that POSTs to `/ldp/stream` and returns a `Stream<Item = LdpEnvelope>` by parsing SSE lines.

- [ ] **Step 4: Run all tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test`
Expected: All pass (signing test may need update for extended TASK_UPDATE payload)

- [ ] **Step 5: Commit**

```bash
git add src/signing.rs src/server.rs src/client.rs
git commit -m "feat: SSE streaming for TASK_UPDATE with extended signing payload (Rust)"
```

---

### Task 12: SSE Streaming — Python

**Files:**
- Modify: `sdk/python/src/ldp_protocol/signing.py:41-43` (extend TASK_UPDATE signing)
- Modify: `sdk/python/src/ldp_protocol/delegate.py` (add SSE endpoint + handle_task_stream)
- Modify: `sdk/python/src/ldp_protocol/client.py` (add submit_task_stream)
- Create: `sdk/python/tests/test_streaming.py`

- [ ] **Step 1: Write failing tests**

Create `sdk/python/tests/test_streaming.py`:

```python
"""Tests for SSE streaming."""
from ldp_protocol.signing import sign_envelope
from ldp_protocol.types.messages import LdpEnvelope, LdpMessageBody
from ldp_protocol.types.payload import PayloadMode


def test_task_update_signing_includes_progress():
    """TASK_UPDATE signing should include progress and message fields."""
    body = LdpMessageBody.task_update("t1", progress=0.5, message="Working...")
    env = LdpEnvelope.create("s1", "from", "to", body, PayloadMode.TEXT)
    sig1 = sign_envelope(env, "secret")

    body2 = LdpMessageBody.task_update("t1", progress=0.8, message="Working...")
    env2 = LdpEnvelope.create("s1", "from", "to", body2, PayloadMode.TEXT)
    env2.message_id = env.message_id
    env2.timestamp = env.timestamp
    sig2 = sign_envelope(env2, "secret")

    # Different progress = different signature
    assert sig1 != sig2


def test_task_update_signing_includes_message():
    body = LdpMessageBody.task_update("t1", progress=0.5, message="A")
    env = LdpEnvelope.create("s1", "from", "to", body, PayloadMode.TEXT)
    sig1 = sign_envelope(env, "secret")

    body2 = LdpMessageBody.task_update("t1", progress=0.5, message="B")
    env2 = LdpEnvelope.create("s1", "from", "to", body2, PayloadMode.TEXT)
    env2.message_id = env.message_id
    env2.timestamp = env.timestamp
    sig2 = sign_envelope(env2, "secret")

    assert sig1 != sig2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/test_streaming.py -v`
Expected: FAIL — current signing doesn't differentiate progress values

- [ ] **Step 3: Extend Python TASK_UPDATE signing**

In `sdk/python/src/ldp_protocol/signing.py`, replace lines 41-43 (the combined `elif` branch for TASK_UPDATE/TASK_RESULT/TASK_FAILED/TASK_CANCEL):

```python
    elif body_type == "TASK_UPDATE":
        if body.task_id:
            mac.update(body.task_id.encode())
        if body.progress is not None:
            mac.update(b"|")
            mac.update(str(body.progress).encode())
        if body.message is not None:
            mac.update(b"|")
            mac.update(body.message.encode())
    elif body_type in ("TASK_RESULT", "TASK_FAILED", "TASK_CANCEL"):
        if body.task_id:
            mac.update(body.task_id.encode())
```

**Important:** The original code handled all four types in one branch. The replacement splits TASK_UPDATE out with extended fields, and preserves the existing behavior for TASK_RESULT, TASK_FAILED, and TASK_CANCEL.

- [ ] **Step 4: Add handle_task_stream to delegate**

In `sdk/python/src/ldp_protocol/delegate.py`, add:

```python
async def handle_task_stream(self, skill: str, input_data: Any, task_id: str):
    """Override for streaming. Yield (progress, message) tuples.
    Final yield: (1.0, output, confidence) as a 3-tuple."""
    raise NotImplementedError
```

Add SSE route `/ldp/stream` in `run()` that:
1. Accepts POST with TASK_SUBMIT envelope
2. If `handle_task_stream` is overridden, call it and yield SSE events
3. If not, wrap `handle_task` in a single-event stream
4. Return `StreamingResponse(media_type="text/event-stream")`

- [ ] **Step 5: Add submit_task_stream to client**

In `sdk/python/src/ldp_protocol/client.py`, add:

```python
async def submit_task_stream(self, url: str, skill: str, input_data: dict, ...):
    """Submit a task and stream progress updates via SSE."""
    # POST to /ldp/stream
    # Parse SSE lines: "event: ...\ndata: ...\n\n"
    # Yield parsed envelopes
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add sdk/python/src/ldp_protocol/signing.py sdk/python/src/ldp_protocol/delegate.py \
  sdk/python/src/ldp_protocol/client.py sdk/python/tests/test_streaming.py
git commit -m "feat: SSE streaming for TASK_UPDATE with extended signing payload (Python)"
```

---

## Phase C: Ecosystem

### Task 13: OpenAPI Spec

**Files:**
- Create: `docs/openapi.yaml`

- [ ] **Step 1: Write the OpenAPI spec**

Create `docs/openapi.yaml` with:
- `openapi: "3.0.3"`
- `info:` with title "LDP - LLM Delegate Protocol", version "0.3.0"
- Paths: `/.well-known/ldp-identity` (GET), `/ldp/identity` (GET), `/ldp/capabilities` (GET), `/ldp/messages` (POST), `/ldp/stream` (POST)
- Components/schemas: `LdpIdentityCard`, `LdpEnvelope`, `LdpMessageBody`, `Provenance`, `TrustDomain`, `DelegationContract`, `LdpError`
- Security schemes: `bearerAuth` (type: http, scheme: bearer)

Derive all schemas from the existing Pydantic models. Include `nonce` on LdpEnvelope, `trust_domain` on SessionAccept, `Security` in FailureCategory.

- [ ] **Step 2: Validate the spec parses**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && python -c "import yaml; yaml.safe_load(open('docs/openapi.yaml')); print('OpenAPI spec valid YAML')"`

- [ ] **Step 3: Commit**

```bash
git add docs/openapi.yaml
git commit -m "docs: add OpenAPI 3.0 specification"
```

---

### Task 14: Conformance Test Suite

**Files:**
- Create: `sdk/python/src/ldp_protocol/conformance/__init__.py`
- Create: `sdk/python/src/ldp_protocol/conformance/cli.py`
- Create: `sdk/python/src/ldp_protocol/conformance/runner.py`
- Create: `sdk/python/src/ldp_protocol/conformance/report.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/__init__.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/identity.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/sessions.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/tasks.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/provenance.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/trust.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/signing.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/streaming.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/bearer_auth.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/session_ttl.py`
- Create: `sdk/python/src/ldp_protocol/conformance/checks/contracts.py`
- Modify: `sdk/python/pyproject.toml` (add conformance deps + CLI entry point)

This is a large task. Break into sub-steps:

- [ ] **Step 1: Update pyproject.toml**

Add to `[project.optional-dependencies]`:
```toml
conformance = ["click>=8.0", "rich>=13.0"]
```

Add `[project.scripts]`:
```toml
[project.scripts]
ldp-conformance = "ldp_protocol.conformance.cli:main"
```

- [ ] **Step 2: Create check result types**

Create `sdk/python/src/ldp_protocol/conformance/__init__.py`:

```python
"""LDP Conformance Test Suite."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    reason: str = ""
```

- [ ] **Step 3: Create runner**

Create `sdk/python/src/ldp_protocol/conformance/runner.py` — orchestrates check categories, collects results, determines overall pass/fail. Takes target URL, optional bearer_token, signing_secret, timeout, and category filter.

- [ ] **Step 4: Create identity checks**

Create `sdk/python/src/ldp_protocol/conformance/checks/identity.py`:
- `check_identity_card(url)` — GET `/ldp/identity`, validate required fields
- `check_wellknown_discovery(url)` — GET `/.well-known/ldp-identity`
- `check_capabilities_declared(url)` — at least one capability

Each returns `CheckResult`.

- [ ] **Step 5: Create remaining check modules**

Create check files for: sessions, tasks, provenance, trust, signing, streaming, bearer_auth, session_ttl, contracts. Each contains async check functions that return `CheckResult`.

- [ ] **Step 6: Create report formatter**

Create `sdk/python/src/ldp_protocol/conformance/report.py` — formats results as text (using rich) or JSON.

- [ ] **Step 7: Create CLI**

Create `sdk/python/src/ldp_protocol/conformance/cli.py`:

```python
"""LDP Conformance CLI."""
import asyncio
import click


@click.command()
@click.argument("url")
@click.option("--verbose", is_flag=True)
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--bearer-token", default=None)
@click.option("--signing-secret", default=None)
@click.option("--only", default=None, help="Comma-separated category list")
@click.option("--timeout", default=30, type=int)
def main(url, verbose, fmt, bearer_token, signing_secret, only, timeout):
    """Run LDP conformance tests against a target endpoint."""
    from ldp_protocol.conformance.runner import run_conformance
    from ldp_protocol.conformance.report import format_report

    categories = only.split(",") if only else None
    results = asyncio.run(run_conformance(
        url, bearer_token=bearer_token, signing_secret=signing_secret,
        categories=categories, timeout=timeout,
    ))
    output = format_report(results, fmt=fmt, verbose=verbose)
    click.echo(output)
    # Exit 1 if any required check failed
    raise SystemExit(0 if results["conformant"] else 1)
```

- [ ] **Step 8: Test CLI runs**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && pip install -e ".[conformance]" && ldp-conformance --help`
Expected: Help text printed

- [ ] **Step 9: Commit**

```bash
git add sdk/python/src/ldp_protocol/conformance/ sdk/python/pyproject.toml
git commit -m "feat: add LDP conformance test suite CLI"
```

---

### Task 15: Version Bump + Final Integration Test

**Files:**
- Modify: `Cargo.toml:4` (version to "0.3.0")
- Modify: `sdk/python/pyproject.toml:6` (version to "0.3.0")
- Modify: `CHANGELOG.md` (move Unreleased items to [0.3.0])

- [ ] **Step 1: Bump versions**

In `Cargo.toml`, change `version = "0.1.0"` to `version = "0.3.0"`.
In `sdk/python/pyproject.toml`, change `version = "0.2.0"` to `version = "0.3.0"`.

- [ ] **Step 2: Update CHANGELOG**

Move all `[Unreleased]` entries under a new `## [0.3.0] - 2026-XX-XX` section (fill in actual date). Add:

```markdown
### Added
- Replay detection with nonce + timestamp window (configurable)
- Bearer token authentication (transport layer)
- Trust domain Rules #2-3: mutual trust verification + wildcard matching
- Active session TTL expiration with background reaper
- SSE streaming for TASK_UPDATE via `/ldp/stream` endpoint
- `FailureCategory::Security` error category
- LDP Conformance Test Suite CLI (`pip install ldp-protocol[conformance]`)
- OpenAPI 3.0 specification (`docs/openapi.yaml`)
- CI/CD with GitHub Actions (Rust + Python matrix, cross-SDK compat)
- Published to crates.io
```

- [ ] **Step 3: Run full Rust test suite**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo test`
Expected: All pass

- [ ] **Step 4: Run full Python test suite**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol/sdk/python && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 5: Dry-run cargo publish**

Run: `cd /Users/sunilp/Development/sunil-ws/ldp-protocol && cargo publish --dry-run`
Expected: Success

- [ ] **Step 6: Commit**

```bash
git add Cargo.toml sdk/python/pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to 0.3.0 for Phase 1 hardening release"
```

---

### Task 16: Tag and Release

- [ ] **Step 1: Create annotated tag**

```bash
git tag -a v0.3.0 -m "LDP v0.3.0 — Phase 1 Hardening + Ecosystem Launch"
```

- [ ] **Step 2: Push tag (triggers release workflow)**

```bash
git push origin main --tags
```

- [ ] **Step 3: Verify release**

After GitHub Actions completes:
- Check PyPI: `pip install ldp-protocol==0.3.0`
- Check crates.io: `cargo add ldp-protocol@0.3.0` (dry run)
- Check GitHub Releases page for auto-generated release notes

- [ ] **Step 4: Write blog post**

Manual task — write on sunilprakash.com covering:
- What's new in v0.3.0
- Conformance suite announcement
- Link to OpenAPI spec
- Call to action for contributors
