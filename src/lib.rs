//! JamJet LDP Protocol Adapter
//!
//! Implements the LLM Delegate Protocol (LDP) as a JamJet protocol adapter,
//! alongside existing MCP and A2A adapters.
//!
//! # Architecture
//!
//! The adapter follows JamJet's `ProtocolAdapter` trait pattern:
//!
//! ```text
//! JamJet Workflow Engine
//!   ↓ discover / invoke / stream / status / cancel
//! LdpAdapter (ProtocolAdapter impl)
//!   ↓ manages sessions transparently
//! SessionManager
//!   ↓ HELLO → SESSION_PROPOSE → SESSION_ACCEPT → TASK_SUBMIT
//! LdpClient (HTTP)
//!   ↓
//! Remote LDP Delegate
//! ```
//!
//! # Key Design Decisions
//!
//! - **Sessions are transparent**: JamJet's workflow engine sees request→response.
//!   The adapter handles session lifecycle internally.
//! - **AgentCard extension**: LDP identity fields go in `AgentCard.labels` with
//!   `ldp.*` keys. A full `LdpIdentityCard` is maintained internally.
//! - **Provenance embedded in output**: Every completed task carries provenance
//!   metadata in the output `Value`, flowing through JamJet's existing pipeline.
//! - **Trust domain enforcement**: Validated during `discover()` before any
//!   session is established.

pub mod adapter;
pub mod client;
pub mod config;
pub mod plugin;
pub mod server;
pub mod session_manager;
pub mod types;

pub use adapter::LdpAdapter;
pub use client::LdpClient;
pub use config::LdpAdapterConfig;
pub use plugin::register_ldp;
pub use server::LdpServer;
pub use session_manager::SessionManager;
pub use types::*;
