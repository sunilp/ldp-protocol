//! Standalone protocol abstractions for LDP.
//!
//! These types define the adapter interface for LDP, allowing it to operate
//! independently or as a plugin within runtimes like JamJet.

use crate::types::error::LdpError;
use async_trait::async_trait;
use futures::Stream;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::pin::Pin;

/// A skill exposed by a remote delegate.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteSkill {
    /// Skill name (e.g., "reasoning", "summarization").
    pub name: String,
    /// Human-readable description.
    pub description: Option<String>,
    /// JSON Schema for expected input.
    pub input_schema: Option<Value>,
    /// JSON Schema for expected output.
    pub output_schema: Option<Value>,
}

/// Capabilities discovered from a remote delegate.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemoteCapabilities {
    /// Delegate display name.
    pub name: String,
    /// Human-readable description.
    pub description: Option<String>,
    /// Available skills.
    pub skills: Vec<RemoteSkill>,
    /// Supported protocols (e.g., `["ldp"]`).
    pub protocols: Vec<String>,
}

/// A request to execute a task on a remote delegate.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskRequest {
    /// The skill to invoke.
    pub skill: String,
    /// Input data for the task.
    pub input: Value,
}

/// Handle returned after submitting a task.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskHandle {
    /// Unique identifier for the submitted task.
    pub task_id: String,
    /// URL of the remote delegate handling the task.
    pub remote_url: String,
}

/// Events emitted during task streaming.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TaskEvent {
    /// Progress update.
    Progress {
        message: String,
        progress: Option<f32>,
    },
    /// Task completed successfully.
    Completed { output: Value },
    /// Task failed.
    Failed { error: LdpError },
}

/// Current status of a submitted task.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TaskStatus {
    /// Task has been submitted but not yet started.
    Submitted,
    /// Task is actively being processed.
    Working,
    /// Task completed with output.
    Completed { output: Value },
    /// Task failed with an error.
    Failed { error: LdpError },
}

/// Async stream of task events.
pub type TaskStream = Pin<Box<dyn Stream<Item = TaskEvent> + Send>>;

/// Protocol adapter trait — the core abstraction for delegate communication.
///
/// Implementations handle the full lifecycle: discovery, invocation, streaming,
/// status polling, and cancellation.
#[async_trait]
pub trait ProtocolAdapter: Send + Sync {
    /// Discover capabilities of a remote delegate.
    async fn discover(&self, url: &str) -> Result<RemoteCapabilities, String>;

    /// Submit a task for execution and return a handle.
    async fn invoke(&self, url: &str, task: TaskRequest) -> Result<TaskHandle, String>;

    /// Submit a task and stream progress events.
    async fn stream(&self, url: &str, task: TaskRequest) -> Result<TaskStream, String>;

    /// Poll the current status of a submitted task.
    async fn status(&self, url: &str, task_id: &str) -> Result<TaskStatus, String>;

    /// Cancel a running task.
    async fn cancel(&self, url: &str, task_id: &str) -> Result<(), String>;
}

/// Registry for protocol adapters, mapping protocol names to implementations.
///
/// Supports URL-based routing: adapters register URL prefixes, and the registry
/// resolves which adapter handles a given URL.
pub struct ProtocolRegistry {
    adapters: Vec<(String, std::sync::Arc<dyn ProtocolAdapter>, Vec<String>)>,
}

impl ProtocolRegistry {
    /// Create an empty registry.
    pub fn new() -> Self {
        Self {
            adapters: Vec::new(),
        }
    }

    /// Register an adapter with a protocol name and URL prefixes.
    pub fn register(
        &mut self,
        name: &str,
        adapter: std::sync::Arc<dyn ProtocolAdapter>,
        url_prefixes: Vec<&str>,
    ) {
        self.adapters.push((
            name.to_string(),
            adapter,
            url_prefixes.iter().map(|s| s.to_string()).collect(),
        ));
    }

    /// Look up an adapter by protocol name.
    pub fn adapter(&self, name: &str) -> Option<&dyn ProtocolAdapter> {
        self.adapters
            .iter()
            .find(|(n, _, _)| n == name)
            .map(|(_, a, _)| a.as_ref())
    }

    /// Find the adapter that handles a given URL.
    pub fn adapter_for_url(&self, url: &str) -> Option<&dyn ProtocolAdapter> {
        self.adapters
            .iter()
            .find(|(_, _, prefixes)| prefixes.iter().any(|p| url.starts_with(p)))
            .map(|(_, a, _)| a.as_ref())
    }

    /// List all registered protocol names.
    pub fn protocols(&self) -> Vec<&str> {
        self.adapters.iter().map(|(n, _, _)| n.as_str()).collect()
    }
}

impl Default for ProtocolRegistry {
    fn default() -> Self {
        Self::new()
    }
}
