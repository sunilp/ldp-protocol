//! LDP session types.
//!
//! Sessions are governed multi-round contexts — the key difference from
//! stateless A2A/MCP invocations. Session management is internal to the
//! adapter; JamJet's workflow engine sees only request→response.

use crate::types::payload::NegotiatedPayload;
use crate::types::trust::TrustDomain;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// State of an LDP session.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    /// HELLO sent, waiting for response.
    Initiating,
    /// Session proposed, awaiting acceptance.
    Proposed,
    /// Session active — tasks can be submitted.
    Active,
    /// Session suspended (can be resumed).
    Suspended,
    /// Session terminated.
    Closed,
    /// Session failed to establish.
    Failed,
}

/// An active LDP session.
///
/// Sessions are cached by the `SessionManager` and reused across
/// multiple `invoke()` calls to the same delegate.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpSession {
    /// Unique session identifier.
    pub session_id: String,

    /// Remote delegate endpoint.
    pub remote_url: String,

    /// Remote delegate ID.
    pub remote_delegate_id: String,

    /// Current session state.
    pub state: SessionState,

    /// Negotiated payload mode for this session.
    pub payload: NegotiatedPayload,

    /// Trust domain of the remote delegate.
    pub trust_domain: TrustDomain,

    /// When the session was established.
    pub created_at: DateTime<Utc>,

    /// When the session was last used.
    pub last_used: DateTime<Utc>,

    /// Session TTL in seconds (after which it expires if unused).
    pub ttl_secs: u64,

    /// Number of tasks submitted in this session.
    pub task_count: u64,
}

impl LdpSession {
    /// Check if the session is still active and not expired.
    pub fn is_active(&self) -> bool {
        if self.state != SessionState::Active {
            return false;
        }
        let elapsed = Utc::now()
            .signed_duration_since(self.last_used)
            .num_seconds();
        elapsed < self.ttl_secs as i64
    }

    /// Touch the session (update last_used timestamp).
    pub fn touch(&mut self) {
        self.last_used = Utc::now();
    }
}

/// Configuration for establishing a new LDP session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionConfig {
    /// Preferred payload modes, ordered by preference.
    pub preferred_payload_modes: Vec<crate::types::payload::PayloadMode>,

    /// Session TTL in seconds.
    pub ttl_secs: u64,

    /// Trust domain requirement (if set, only delegates in this domain are accepted).
    pub required_trust_domain: Option<String>,
}

impl Default for SessionConfig {
    fn default() -> Self {
        Self {
            preferred_payload_modes: vec![
                crate::types::payload::PayloadMode::SemanticFrame,
                crate::types::payload::PayloadMode::Text,
            ],
            ttl_secs: 3600, // 1 hour default
            required_trust_domain: None,
        }
    }
}
