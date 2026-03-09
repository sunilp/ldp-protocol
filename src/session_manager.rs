//! LDP session cache and lifecycle management.
//!
//! The session manager is the key architectural component that makes LDP
//! sessions transparent to JamJet's workflow engine. From the outside,
//! `invoke()` is request→response. Internally, the session manager handles:
//!
//! 1. Check if a session exists for (url, config) pair
//! 2. If not, run HELLO → CAPABILITY_MANIFEST → SESSION_PROPOSE → SESSION_ACCEPT
//! 3. Cache the session
//! 4. Return the active session for task submission

use crate::client::LdpClient;
use crate::config::LdpAdapterConfig;
use crate::types::messages::{LdpEnvelope, LdpMessageBody};
use crate::types::payload::{negotiate_payload_mode, PayloadMode};
use crate::types::session::{LdpSession, SessionState};
use crate::types::trust::TrustDomain;
use chrono::Utc;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info};

/// Manages LDP session lifecycle and caching.
///
/// Thread-safe: uses `RwLock` internally.
#[derive(Clone)]
pub struct SessionManager {
    /// Active sessions keyed by remote URL.
    sessions: Arc<RwLock<HashMap<String, LdpSession>>>,
    /// LDP HTTP client for protocol messages.
    client: LdpClient,
    /// Adapter configuration.
    config: LdpAdapterConfig,
}

impl SessionManager {
    /// Create a new session manager.
    pub fn new(client: LdpClient, config: LdpAdapterConfig) -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            client,
            config,
        }
    }

    /// Get or establish a session for the given remote URL.
    ///
    /// If an active, non-expired session exists, returns it.
    /// Otherwise, runs the full handshake sequence.
    pub async fn get_or_establish(&self, url: &str) -> Result<LdpSession, String> {
        // Check for existing active session.
        {
            let sessions = self.sessions.read().await;
            if let Some(session) = sessions.get(url) {
                if session.is_active() {
                    debug!(url = %url, session_id = %session.session_id, "Reusing existing LDP session");
                    return Ok(session.clone());
                }
                debug!(url = %url, "Existing session expired or inactive, establishing new one");
            }
        }

        // Establish a new session.
        let session = self.establish_session(url).await?;

        // Cache it.
        {
            let mut sessions = self.sessions.write().await;
            sessions.insert(url.to_string(), session.clone());
        }

        Ok(session)
    }

    /// Run the full LDP session establishment handshake:
    /// HELLO → CAPABILITY_MANIFEST → SESSION_PROPOSE → SESSION_ACCEPT
    async fn establish_session(&self, url: &str) -> Result<LdpSession, String> {
        let session_config = &self.config.session;
        let our_delegate_id = &self.config.delegate_id;

        info!(url = %url, "Establishing new LDP session");

        // Step 1: Send HELLO
        let hello = LdpEnvelope::new(
            "", // No session yet
            our_delegate_id,
            url,
            LdpMessageBody::Hello {
                delegate_id: our_delegate_id.clone(),
                supported_modes: session_config.preferred_payload_modes.clone(),
            },
            PayloadMode::Text,
        );

        let hello_response = self.client.send_message(url, &hello).await?;

        // Step 2: Parse CAPABILITY_MANIFEST response
        let remote_modes = match &hello_response.body {
            LdpMessageBody::CapabilityManifest { capabilities } => {
                // Extract supported modes from capability manifest.
                capabilities
                    .get("supported_modes")
                    .and_then(|v| serde_json::from_value::<Vec<PayloadMode>>(v.clone()).ok())
                    .unwrap_or_else(|| vec![PayloadMode::Text])
            }
            other => {
                return Err(format!(
                    "Expected CAPABILITY_MANIFEST response to HELLO, got: {:?}",
                    std::mem::discriminant(other)
                ));
            }
        };

        let remote_delegate_id = hello_response.from.clone();

        // Step 3: Negotiate payload mode
        let negotiated = negotiate_payload_mode(
            &session_config.preferred_payload_modes,
            &remote_modes,
        );

        debug!(
            mode = %negotiated.mode,
            fallbacks = ?negotiated.fallback_chain,
            "Payload mode negotiated"
        );

        // Step 4: Trust domain check
        let remote_trust_domain = hello_response
            .provenance
            .as_ref()
            .map(|p| p.produced_by.clone())
            .unwrap_or_default();

        if let Some(ref required_domain) = session_config.required_trust_domain {
            if remote_trust_domain != *required_domain && !remote_trust_domain.is_empty() {
                return Err(format!(
                    "Trust domain mismatch: required {}, got {}",
                    required_domain, remote_trust_domain
                ));
            }
        }

        // Step 5: Send SESSION_PROPOSE
        let session_id = uuid::Uuid::new_v4().to_string();
        let propose = LdpEnvelope::new(
            &session_id,
            our_delegate_id,
            &remote_delegate_id,
            LdpMessageBody::SessionPropose {
                config: serde_json::json!({
                    "payload_mode": negotiated.mode,
                    "ttl_secs": session_config.ttl_secs,
                }),
            },
            PayloadMode::Text,
        );

        let propose_response = self.client.send_message(url, &propose).await?;

        // Step 6: Handle SESSION_ACCEPT or SESSION_REJECT
        match &propose_response.body {
            LdpMessageBody::SessionAccept {
                session_id: accepted_id,
                negotiated_mode,
            } => {
                info!(
                    session_id = %accepted_id,
                    mode = %negotiated_mode,
                    "LDP session established"
                );

                let now = Utc::now();
                Ok(LdpSession {
                    session_id: accepted_id.clone(),
                    remote_url: url.to_string(),
                    remote_delegate_id,
                    state: SessionState::Active,
                    payload: negotiated,
                    trust_domain: TrustDomain::new(remote_trust_domain),
                    created_at: now,
                    last_used: now,
                    ttl_secs: session_config.ttl_secs,
                    task_count: 0,
                })
            }
            LdpMessageBody::SessionReject { reason } => {
                Err(format!("Session rejected by remote: {}", reason))
            }
            other => Err(format!(
                "Expected SESSION_ACCEPT/REJECT, got: {:?}",
                std::mem::discriminant(other)
            )),
        }
    }

    /// Mark a session as used (touch timestamp, increment task count).
    pub async fn touch(&self, url: &str) {
        let mut sessions = self.sessions.write().await;
        if let Some(session) = sessions.get_mut(url) {
            session.touch();
            session.task_count += 1;
        }
    }

    /// Close a session.
    pub async fn close(&self, url: &str) -> Result<(), String> {
        let session = {
            let mut sessions = self.sessions.write().await;
            sessions.remove(url)
        };

        if let Some(session) = session {
            let close_msg = LdpEnvelope::new(
                &session.session_id,
                &self.config.delegate_id,
                &session.remote_delegate_id,
                LdpMessageBody::SessionClose { reason: None },
                session.payload.mode,
            );
            // Best-effort close — don't fail if remote is unreachable.
            let _ = self.client.send_message(url, &close_msg).await;
            info!(session_id = %session.session_id, "LDP session closed");
        }

        Ok(())
    }

    /// Close all sessions.
    pub async fn close_all(&self) {
        let urls: Vec<String> = {
            let sessions = self.sessions.read().await;
            sessions.keys().cloned().collect()
        };
        for url in urls {
            let _ = self.close(&url).await;
        }
    }

    /// Get the number of active sessions.
    pub async fn active_count(&self) -> usize {
        let sessions = self.sessions.read().await;
        sessions.values().filter(|s| s.is_active()).count()
    }
}
