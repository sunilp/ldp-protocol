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
