//! LDP server — receives LDP messages and serves identity/capabilities.
//!
//! A minimal LDP-compliant server that:
//! - Serves identity cards at `GET /ldp/identity`
//! - Serves capabilities at `GET /ldp/capabilities`
//! - Handles protocol messages at `POST /ldp/messages`
//! - Manages session lifecycle (accept/reject)
//! - Dispatches tasks to a pluggable handler

use crate::types::capability::LdpCapability;
use crate::types::identity::LdpIdentityCard;
use crate::types::messages::{LdpEnvelope, LdpMessageBody};
use crate::types::payload::{negotiate_payload_mode, PayloadMode};
use crate::types::provenance::Provenance;
use crate::types::session::{LdpSession, SessionState};
use crate::types::trust::TrustDomain;

use chrono::Utc;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info};

/// Task handler function type.
///
/// Given a skill name and input, returns the output value.
/// Used to plug in actual task execution logic.
pub type TaskHandler = Arc<dyn Fn(&str, &Value) -> Value + Send + Sync>;

/// A minimal LDP server for testing and research.
pub struct LdpServer {
    /// This server's identity card.
    identity: LdpIdentityCard,
    /// Active sessions.
    sessions: Arc<RwLock<HashMap<String, LdpSession>>>,
    /// Pending/completed tasks: task_id → (state, output).
    tasks: Arc<RwLock<HashMap<String, TaskRecord>>>,
    /// Pluggable task handler.
    handler: TaskHandler,
}

/// Internal task tracking record.
#[derive(Debug, Clone)]
#[allow(dead_code)]
struct TaskRecord {
    task_id: String,
    skill: String,
    state: TaskRecordState,
    output: Option<Value>,
    error: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
#[allow(dead_code)]
enum TaskRecordState {
    Submitted,
    Working,
    Completed,
    Failed,
}

impl LdpServer {
    /// Create a new LDP server with the given identity and task handler.
    pub fn new(identity: LdpIdentityCard, handler: TaskHandler) -> Self {
        Self {
            identity,
            sessions: Arc::new(RwLock::new(HashMap::new())),
            tasks: Arc::new(RwLock::new(HashMap::new())),
            handler,
        }
    }

    /// Create a test server with an echo handler (returns input as output).
    pub fn echo_server(delegate_id: &str, name: &str) -> Self {
        let identity = LdpIdentityCard {
            delegate_id: delegate_id.to_string(),
            name: name.to_string(),
            description: Some("Echo test server".into()),
            model_family: "TestModel".into(),
            model_version: "1.0".into(),
            weights_fingerprint: None,
            trust_domain: TrustDomain::new("test-domain"),
            context_window: 4096,
            reasoning_profile: Some("analytical".into()),
            cost_profile: Some("low".into()),
            latency_profile: Some("p50:100ms".into()),
            jurisdiction: None,
            capabilities: vec![LdpCapability {
                name: "echo".into(),
                description: Some("Echoes input back".into()),
                input_schema: None,
                output_schema: None,
                quality: None,
                domains: vec![],
            }],
            supported_payload_modes: vec![PayloadMode::SemanticFrame, PayloadMode::Text],
            endpoint: String::new(),
            metadata: HashMap::new(),
        };

        let handler: TaskHandler = Arc::new(|_skill, input| {
            json!({ "echo": input })
        });

        Self::new(identity, handler)
    }

    /// Get the identity card.
    pub fn identity(&self) -> &LdpIdentityCard {
        &self.identity
    }

    /// Handle a GET /ldp/identity request.
    pub fn handle_identity_request(&self) -> Value {
        serde_json::to_value(&self.identity).unwrap_or_default()
    }

    /// Handle a GET /ldp/capabilities request.
    pub fn handle_capabilities_request(&self) -> Value {
        json!({
            "capabilities": self.identity.capabilities,
            "supported_modes": self.identity.supported_payload_modes,
        })
    }

    /// Handle a POST /ldp/messages request.
    ///
    /// Processes the incoming LDP envelope and returns a response envelope.
    pub async fn handle_message(&self, envelope: LdpEnvelope) -> Result<LdpEnvelope, String> {
        match &envelope.body {
            LdpMessageBody::Hello { delegate_id, supported_modes } => {
                self.handle_hello(&envelope, delegate_id, supported_modes).await
            }
            LdpMessageBody::SessionPropose { config } => {
                self.handle_session_propose(&envelope, config).await
            }
            LdpMessageBody::TaskSubmit { task_id, skill, input } => {
                self.handle_task_submit(&envelope, task_id, skill, input).await
            }
            LdpMessageBody::TaskUpdate { task_id, .. } => {
                self.handle_task_status_query(&envelope, task_id).await
            }
            LdpMessageBody::TaskCancel { task_id } => {
                self.handle_task_cancel(&envelope, task_id).await
            }
            LdpMessageBody::SessionClose { .. } => {
                self.handle_session_close(&envelope).await
            }
            _ => Err(format!("Unhandled message type")),
        }
    }

    /// Handle HELLO — respond with CAPABILITY_MANIFEST.
    async fn handle_hello(
        &self,
        envelope: &LdpEnvelope,
        _delegate_id: &str,
        _supported_modes: &[PayloadMode],
    ) -> Result<LdpEnvelope, String> {
        info!(from = %envelope.from, "Received HELLO");

        Ok(LdpEnvelope::new(
            &envelope.session_id,
            &self.identity.delegate_id,
            &envelope.from,
            LdpMessageBody::CapabilityManifest {
                capabilities: json!({
                    "capabilities": self.identity.capabilities,
                    "supported_modes": self.identity.supported_payload_modes,
                }),
            },
            PayloadMode::Text,
        ))
    }

    /// Handle SESSION_PROPOSE — accept the session.
    async fn handle_session_propose(
        &self,
        envelope: &LdpEnvelope,
        config: &Value,
    ) -> Result<LdpEnvelope, String> {
        let session_id = envelope.session_id.clone();
        info!(session_id = %session_id, from = %envelope.from, "Session proposed");

        // Extract requested payload mode (default to SemanticFrame).
        let requested_mode = config
            .get("payload_mode")
            .and_then(|v| serde_json::from_value::<PayloadMode>(v.clone()).ok())
            .unwrap_or(PayloadMode::SemanticFrame);

        // Negotiate payload mode.
        let negotiated = negotiate_payload_mode(
            &[requested_mode, PayloadMode::Text],
            &self.identity.supported_payload_modes,
        );

        // Create session.
        let now = Utc::now();
        let ttl = config
            .get("ttl_secs")
            .and_then(|v| v.as_u64())
            .unwrap_or(3600);

        let session = LdpSession {
            session_id: session_id.clone(),
            remote_url: String::new(),
            remote_delegate_id: envelope.from.clone(),
            state: SessionState::Active,
            payload: negotiated.clone(),
            trust_domain: self.identity.trust_domain.clone(),
            created_at: now,
            last_used: now,
            ttl_secs: ttl,
            task_count: 0,
        };

        {
            let mut sessions = self.sessions.write().await;
            sessions.insert(session_id.clone(), session);
        }

        let response = LdpEnvelope::new(
            &session_id,
            &self.identity.delegate_id,
            &envelope.from,
            LdpMessageBody::SessionAccept {
                session_id: session_id.clone(),
                negotiated_mode: negotiated.mode,
            },
            PayloadMode::Text,
        );
        Ok(response)
    }

    /// Handle TASK_SUBMIT — execute the task immediately and return result.
    async fn handle_task_submit(
        &self,
        envelope: &LdpEnvelope,
        task_id: &str,
        skill: &str,
        input: &Value,
    ) -> Result<LdpEnvelope, String> {
        debug!(task_id = %task_id, skill = %skill, "Task submitted");

        // Execute the task using the handler.
        let output = (self.handler)(skill, input);

        // Store the task record.
        {
            let mut tasks = self.tasks.write().await;
            tasks.insert(
                task_id.to_string(),
                TaskRecord {
                    task_id: task_id.to_string(),
                    skill: skill.to_string(),
                    state: TaskRecordState::Completed,
                    output: Some(output.clone()),
                    error: None,
                },
            );
        }

        // Build provenance.
        let provenance = Provenance::new(
            &self.identity.delegate_id,
            &self.identity.model_version,
        );

        // Determine payload mode from session.
        let mode = {
            let sessions = self.sessions.read().await;
            sessions
                .get(&envelope.session_id)
                .map(|s| s.payload.mode)
                .unwrap_or(PayloadMode::Text)
        };

        Ok(LdpEnvelope::new(
            &envelope.session_id,
            &self.identity.delegate_id,
            &envelope.from,
            LdpMessageBody::TaskResult {
                task_id: task_id.to_string(),
                output,
                provenance,
            },
            mode,
        ))
    }

    /// Handle task status query — return current task state.
    async fn handle_task_status_query(
        &self,
        envelope: &LdpEnvelope,
        task_id: &str,
    ) -> Result<LdpEnvelope, String> {
        let tasks = self.tasks.read().await;

        if let Some(record) = tasks.get(task_id) {
            let body = match record.state {
                TaskRecordState::Completed => LdpMessageBody::TaskResult {
                    task_id: task_id.to_string(),
                    output: record.output.clone().unwrap_or(json!(null)),
                    provenance: Provenance::new(
                        &self.identity.delegate_id,
                        &self.identity.model_version,
                    ),
                },
                TaskRecordState::Failed => LdpMessageBody::TaskFailed {
                    task_id: task_id.to_string(),
                    error: record.error.clone().unwrap_or("unknown error".into()),
                },
                _ => LdpMessageBody::TaskUpdate {
                    task_id: task_id.to_string(),
                    progress: None,
                    message: Some(format!("{:?}", record.state).to_lowercase()),
                },
            };

            Ok(LdpEnvelope::new(
                &envelope.session_id,
                &self.identity.delegate_id,
                &envelope.from,
                body,
                PayloadMode::Text,
            ))
        } else {
            Err(format!("Unknown task: {}", task_id))
        }
    }

    /// Handle TASK_CANCEL.
    async fn handle_task_cancel(
        &self,
        envelope: &LdpEnvelope,
        task_id: &str,
    ) -> Result<LdpEnvelope, String> {
        info!(task_id = %task_id, "Task cancelled");

        let mut tasks = self.tasks.write().await;
        tasks.remove(task_id);

        Ok(LdpEnvelope::new(
            &envelope.session_id,
            &self.identity.delegate_id,
            &envelope.from,
            LdpMessageBody::TaskFailed {
                task_id: task_id.to_string(),
                error: "cancelled".into(),
            },
            PayloadMode::Text,
        ))
    }

    /// Handle SESSION_CLOSE.
    async fn handle_session_close(
        &self,
        envelope: &LdpEnvelope,
    ) -> Result<LdpEnvelope, String> {
        info!(session_id = %envelope.session_id, "Session closed");

        let mut sessions = self.sessions.write().await;
        sessions.remove(&envelope.session_id);

        Ok(LdpEnvelope::new(
            &envelope.session_id,
            &self.identity.delegate_id,
            &envelope.from,
            LdpMessageBody::SessionClose {
                reason: Some("acknowledged".into()),
            },
            PayloadMode::Text,
        ))
    }

    /// Get active session count.
    pub async fn active_sessions(&self) -> usize {
        self.sessions.read().await.len()
    }

    /// Get completed task count.
    pub async fn completed_tasks(&self) -> usize {
        self.tasks
            .read()
            .await
            .values()
            .filter(|t| t.state == TaskRecordState::Completed)
            .count()
    }
}
