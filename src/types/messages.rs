//! LDP message types.
//!
//! The LDP message envelope wraps all protocol messages with routing,
//! session context, and provenance metadata.

use crate::types::error::LdpError;
use crate::types::payload::PayloadMode;
use crate::types::provenance::Provenance;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// LDP message envelope — wraps every protocol message.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpEnvelope {
    /// Message ID (UUID).
    pub message_id: String,

    /// Session ID this message belongs to.
    pub session_id: String,

    /// Sender delegate ID.
    pub from: String,

    /// Recipient delegate ID.
    pub to: String,

    /// Message body.
    pub body: LdpMessageBody,

    /// Payload mode used for this message.
    pub payload_mode: PayloadMode,

    /// ISO 8601 timestamp.
    pub timestamp: String,

    /// Optional provenance (attached to results).
    pub provenance: Option<Provenance>,

    /// HMAC signature of the message (hex-encoded).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,

    /// Signature algorithm (e.g., "hmac-sha256").
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature_algorithm: Option<String>,
}

/// LDP message body variants.
///
/// Maps to the LDP RFC message types. DCI interaction moves are carried
/// as TASK_SUBMIT payloads (no new message types needed per integration spec).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "SCREAMING_SNAKE_CASE")]
pub enum LdpMessageBody {
    /// Initial handshake.
    Hello {
        delegate_id: String,
        supported_modes: Vec<PayloadMode>,
    },

    /// Capability manifest response.
    CapabilityManifest { capabilities: Value },

    /// Propose a session with configuration.
    SessionPropose { config: Value },

    /// Accept a proposed session.
    SessionAccept {
        session_id: String,
        negotiated_mode: PayloadMode,
    },

    /// Reject a proposed session.
    SessionReject {
        reason: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        error: Option<LdpError>,
    },

    /// Submit a task within a session.
    TaskSubmit {
        task_id: String,
        skill: String,
        input: Value,
    },

    /// Task progress update.
    TaskUpdate {
        task_id: String,
        progress: Option<f32>,
        message: Option<String>,
    },

    /// Task result.
    TaskResult {
        task_id: String,
        output: Value,
        provenance: Provenance,
    },

    /// Task failure.
    TaskFailed { task_id: String, error: LdpError },

    /// Task cancellation request.
    TaskCancel { task_id: String },

    /// Attestation (trust signal).
    Attestation { claim: Value, evidence: Value },

    /// Session close.
    SessionClose { reason: Option<String> },
}

impl LdpEnvelope {
    /// Create a new envelope with auto-generated message ID and timestamp.
    pub fn new(
        session_id: impl Into<String>,
        from: impl Into<String>,
        to: impl Into<String>,
        body: LdpMessageBody,
        payload_mode: PayloadMode,
    ) -> Self {
        Self {
            message_id: uuid::Uuid::new_v4().to_string(),
            session_id: session_id.into(),
            from: from.into(),
            to: to.into(),
            body,
            payload_mode,
            timestamp: chrono::Utc::now().to_rfc3339(),
            provenance: None,
            signature: None,
            signature_algorithm: None,
        }
    }
}
