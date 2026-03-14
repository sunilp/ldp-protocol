//! LDP protocol adapter — implements the `ProtocolAdapter` trait.
//!
//! This is the primary integration point. The adapter:
//! - Translates `discover/invoke/stream/status/cancel` into LDP messages
//! - Manages sessions transparently (callers see request->response)
//! - Attaches provenance to all results
//! - Enforces trust domain boundaries

use crate::client::LdpClient;
use crate::config::LdpAdapterConfig;
use crate::protocol::{
    ProtocolAdapter, RemoteCapabilities, RemoteSkill, TaskEvent, TaskHandle, TaskRequest,
    TaskStatus, TaskStream,
};
use crate::session_manager::SessionManager;
use crate::types::messages::{LdpEnvelope, LdpMessageBody};
use crate::types::provenance::Provenance;

use async_trait::async_trait;
use serde_json::{json, Value};
use tracing::{debug, info, instrument};

/// LDP protocol adapter.
///
/// Can be used standalone or registered with a `ProtocolRegistry`
/// (including JamJet's registry via the `jamjet` feature).
pub struct LdpAdapter {
    session_manager: SessionManager,
    client: LdpClient,
    config: LdpAdapterConfig,
}

impl LdpAdapter {
    /// Create a new LDP adapter with the given configuration.
    pub fn new(config: LdpAdapterConfig) -> Self {
        let client = LdpClient::new();
        let session_manager = SessionManager::new(client.clone(), config.clone());
        Self {
            session_manager,
            client,
            config,
        }
    }

    /// Create with a custom HTTP client (useful for testing).
    pub fn with_client(config: LdpAdapterConfig, client: LdpClient) -> Self {
        let session_manager = SessionManager::new(client.clone(), config.clone());
        Self {
            session_manager,
            client,
            config,
        }
    }

    /// Get the session manager (for external session control).
    pub fn session_manager(&self) -> &SessionManager {
        &self.session_manager
    }

    /// Convert an LDP identity card to RemoteCapabilities.
    fn identity_to_capabilities(
        &self,
        identity: &crate::types::identity::LdpIdentityCard,
    ) -> RemoteCapabilities {
        let skills = identity
            .capabilities
            .iter()
            .map(|cap| RemoteSkill {
                name: cap.name.clone(),
                description: cap.description.clone(),
                input_schema: cap.input_schema.clone(),
                output_schema: cap.output_schema.clone(),
            })
            .collect();

        RemoteCapabilities {
            name: identity.name.clone(),
            description: identity.description.clone(),
            skills,
            protocols: vec!["ldp".into()],
        }
    }

    /// Embed provenance into a task output Value.
    fn embed_provenance(&self, output: Value, provenance: Provenance) -> Value {
        if self.config.attach_provenance {
            match output {
                Value::Object(mut map) => {
                    map.insert("ldp_provenance".into(), provenance.to_value());
                    Value::Object(map)
                }
                other => {
                    json!({
                        "result": other,
                        "ldp_provenance": provenance.to_value()
                    })
                }
            }
        } else {
            output
        }
    }
}

#[async_trait]
impl ProtocolAdapter for LdpAdapter {
    /// Discover remote delegate capabilities.
    ///
    /// 1. Fetch LDP identity card
    /// 2. Validate trust domain (if configured)
    /// 3. Map to RemoteCapabilities
    #[instrument(skip(self), fields(url = %url))]
    async fn discover(&self, url: &str) -> Result<RemoteCapabilities, String> {
        info!(url = %url, "Discovering LDP delegate");

        // Fetch identity card.
        let identity = self.client.fetch_identity_card(url).await?;

        // Trust domain check.
        if self.config.enforce_trust_domains {
            if let Some(ref required_domain) = self.config.session.required_trust_domain {
                if identity.trust_domain.name != *required_domain {
                    return Err(format!(
                        "Trust domain mismatch: required {}, got {}",
                        required_domain, identity.trust_domain.name
                    ));
                }
            }
        }

        // Convert to RemoteCapabilities.
        let capabilities = self.identity_to_capabilities(&identity);
        debug!(
            name = %capabilities.name,
            skills = capabilities.skills.len(),
            "LDP delegate discovered"
        );

        Ok(capabilities)
    }

    /// Submit a task to an LDP delegate.
    ///
    /// 1. Get or establish session (transparent to caller)
    /// 2. Send TASK_SUBMIT within session
    /// 3. Return TaskHandle
    #[instrument(skip(self, task), fields(url = %url, skill = %task.skill))]
    async fn invoke(&self, url: &str, task: TaskRequest) -> Result<TaskHandle, String> {
        info!(url = %url, skill = %task.skill, "Invoking LDP task");

        // Step 1: Get or establish session.
        let session = self.session_manager.get_or_establish(url).await?;

        // Step 2: Send TASK_SUBMIT.
        let task_id = uuid::Uuid::new_v4().to_string();
        let submit = LdpEnvelope::new(
            &session.session_id,
            &self.config.delegate_id,
            &session.remote_delegate_id,
            LdpMessageBody::TaskSubmit {
                task_id: task_id.clone(),
                skill: task.skill.clone(),
                input: task.input.clone(),
            },
            session.payload.mode,
        );

        let _response = self.client.send_message(url, &submit).await?;

        // Touch session (update last_used, increment task count).
        self.session_manager.touch(url).await;

        debug!(task_id = %task_id, "LDP task submitted");

        Ok(TaskHandle {
            task_id,
            remote_url: url.to_string(),
        })
    }

    /// Stream task progress events.
    ///
    /// Submits the task, then polls for updates until completion.
    /// In a full implementation, this would use SSE or WebSocket.
    #[instrument(skip(self, task), fields(url = %url, skill = %task.skill))]
    async fn stream(&self, url: &str, task: TaskRequest) -> Result<TaskStream, String> {
        let handle = self.invoke(url, task).await?;
        let client = self.client.clone();
        let config = self.config.clone();
        let url = url.to_string();
        let task_id = handle.task_id.clone();

        // Poll-based streaming: periodically check task status.
        // In production, replace with SSE subscription.
        let stream = async_stream::stream! {
            let mut interval = tokio::time::interval(std::time::Duration::from_secs(1));
            loop {
                interval.tick().await;

                // Build a status query envelope.
                let status_query = LdpEnvelope::new(
                    "",
                    &config.delegate_id,
                    &url,
                    LdpMessageBody::TaskUpdate {
                        task_id: task_id.clone(),
                        progress: None,
                        message: Some("status_query".into()),
                    },
                    crate::types::payload::PayloadMode::Text,
                );

                match client.send_message(&url, &status_query).await {
                    Ok(response) => match response.body {
                        LdpMessageBody::TaskUpdate { progress, message, .. } => {
                            yield TaskEvent::Progress {
                                message: message.unwrap_or_default(),
                                progress,
                            };
                        }
                        LdpMessageBody::TaskResult { output, provenance, .. } => {
                            let output_with_provenance = if config.attach_provenance {
                                match output {
                                    Value::Object(mut map) => {
                                        map.insert("ldp_provenance".into(),
                                            provenance.to_value());
                                        Value::Object(map)
                                    }
                                    other => json!({
                                        "result": other,
                                        "ldp_provenance": provenance.to_value()
                                    }),
                                }
                            } else {
                                output
                            };
                            yield TaskEvent::Completed { output: output_with_provenance };
                            break;
                        }
                        LdpMessageBody::TaskFailed { error, .. } => {
                            yield TaskEvent::Failed { error };
                            break;
                        }
                        _ => {}
                    },
                    Err(e) => {
                        yield TaskEvent::Failed { error: e };
                        break;
                    }
                }
            }
        };

        Ok(Box::pin(stream))
    }

    /// Poll task status.
    #[instrument(skip(self), fields(url = %url, task_id = %task_id))]
    async fn status(&self, url: &str, task_id: &str) -> Result<TaskStatus, String> {
        debug!(task_id = %task_id, "Polling LDP task status");

        let query = LdpEnvelope::new(
            "",
            &self.config.delegate_id,
            url,
            LdpMessageBody::TaskUpdate {
                task_id: task_id.to_string(),
                progress: None,
                message: Some("status_query".into()),
            },
            crate::types::payload::PayloadMode::Text,
        );

        let response = self.client.send_message(url, &query).await?;

        match response.body {
            LdpMessageBody::TaskUpdate { message, .. } => {
                let msg = message.unwrap_or_default();
                if msg == "submitted" {
                    Ok(TaskStatus::Submitted)
                } else {
                    Ok(TaskStatus::Working)
                }
            }
            LdpMessageBody::TaskResult { output, provenance, .. } => {
                let output = self.embed_provenance(output, provenance);
                Ok(TaskStatus::Completed { output })
            }
            LdpMessageBody::TaskFailed { error, .. } => Ok(TaskStatus::Failed { error }),
            _ => Ok(TaskStatus::Working),
        }
    }

    /// Cancel a running task.
    #[instrument(skip(self), fields(url = %url, task_id = %task_id))]
    async fn cancel(&self, url: &str, task_id: &str) -> Result<(), String> {
        info!(task_id = %task_id, "Cancelling LDP task");

        let cancel_msg = LdpEnvelope::new(
            "",
            &self.config.delegate_id,
            url,
            LdpMessageBody::TaskCancel {
                task_id: task_id.to_string(),
            },
            crate::types::payload::PayloadMode::Text,
        );

        self.client.send_message(url, &cancel_msg).await?;
        Ok(())
    }
}
