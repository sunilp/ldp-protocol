//! LDP type definitions.
//!
//! Core types for the LLM Delegate Protocol: identity cards, capabilities,
//! sessions, messages, payload modes, provenance, and trust domains.

pub mod capability;
pub mod contract;
pub mod error;
pub mod identity;
pub mod messages;
pub mod payload;
pub mod provenance;
pub mod session;
pub mod trust;

pub use capability::{LdpCapability, QualityMetrics, ClaimType};
pub use contract::{DelegationContract, PolicyEnvelope, FailurePolicy, BudgetPolicy};
pub use error::{LdpError, FailureCategory, ErrorSeverity};
pub use identity::LdpIdentityCard;
pub use messages::{LdpEnvelope, LdpMessageBody};
pub use payload::PayloadMode;
pub use provenance::Provenance;
pub use session::{LdpSession, SessionConfig, SessionState};
pub use trust::TrustDomain;
