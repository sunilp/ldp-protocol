//! LDP type definitions.
//!
//! Core types for the LLM Delegate Protocol: identity cards, capabilities,
//! sessions, messages, payload modes, provenance, and trust domains.

pub mod capability;
pub mod identity;
pub mod messages;
pub mod payload;
pub mod provenance;
pub mod session;
pub mod trust;

pub use capability::{LdpCapability, QualityMetrics};
pub use identity::LdpIdentityCard;
pub use messages::{LdpEnvelope, LdpMessageBody};
pub use payload::PayloadMode;
pub use provenance::Provenance;
pub use session::{LdpSession, SessionConfig, SessionState};
pub use trust::TrustDomain;
