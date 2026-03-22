//! LDP — LLM Delegate Protocol
//!
//! An identity-aware communication protocol for multi-agent LLM systems.
//! LDP adds delegation intelligence on top of agent communication protocols
//! like A2A and MCP: rich identity, progressive payload modes, governed
//! sessions, structured provenance, and trust domains.
//!
//! # Architecture
//!
//! ```text
//! ┌──────────────────────────────────────────┐
//! │  Delegation Intelligence — LDP           │
//! │  (identity, routing, provenance, trust)  │
//! ├──────────────────────────────────────────┤
//! │  Agent Communication — A2A               │
//! ├──────────────────────────────────────────┤
//! │  Tool Integration — MCP                  │
//! └──────────────────────────────────────────┘
//! ```
//!
//! # Quick Start
//!
//! ```rust,ignore
//! use ldp_protocol::{LdpAdapter, LdpAdapterConfig};
//! use ldp_protocol::protocol::{ProtocolAdapter, TaskRequest};
//!
//! let adapter = LdpAdapter::new(LdpAdapterConfig::default());
//! let caps = adapter.discover("http://delegate.example.com").await?;
//! ```
//!
//! # Feature Flags
//!
//! - **`jamjet`** — Enable JamJet runtime integration. Adds `register_ldp_jamjet()`
//!   for plugging LDP into JamJet's `ProtocolRegistry`.

pub mod adapter;
pub mod client;
pub mod config;
pub mod plugin;
pub mod protocol;
pub mod server;
pub mod session_manager;
pub mod signing;
pub mod replay;
pub mod types;

pub use adapter::LdpAdapter;
pub use client::LdpClient;
pub use config::LdpAdapterConfig;
pub use plugin::{create_adapter, register_ldp};
pub use protocol::{ProtocolAdapter, ProtocolRegistry, RemoteCapabilities, TaskRequest};
pub use server::LdpServer;
pub use session_manager::SessionManager;
pub use signing::{apply_signature, sign_envelope, verify_envelope};
pub use types::*;
