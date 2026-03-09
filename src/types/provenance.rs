//! LDP provenance tracking.
//!
//! Every LDP task result carries provenance metadata: who produced it,
//! which model, what payload mode, confidence, and verification status.

use crate::types::payload::PayloadMode;
use serde::{Deserialize, Serialize};

/// Provenance metadata attached to every LDP task result.
///
/// Embedded in the output `Value` so it flows through JamJet's existing
/// pipeline without modification.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Provenance {
    /// Delegate ID that produced this result.
    pub produced_by: String,

    /// Model version used.
    pub model_version: String,

    /// Payload mode used for this exchange.
    pub payload_mode_used: PayloadMode,

    /// Self-reported confidence (0.0 – 1.0).
    pub confidence: Option<f64>,

    /// Whether the result has been verified (e.g. by a second delegate).
    pub verified: bool,

    /// Session ID in which this result was produced.
    pub session_id: Option<String>,

    /// Timestamp of production.
    pub timestamp: Option<String>,
}

impl Provenance {
    /// Create a new provenance record.
    pub fn new(delegate_id: impl Into<String>, model_version: impl Into<String>) -> Self {
        Self {
            produced_by: delegate_id.into(),
            model_version: model_version.into(),
            payload_mode_used: PayloadMode::SemanticFrame,
            confidence: None,
            verified: false,
            session_id: None,
            timestamp: Some(chrono::Utc::now().to_rfc3339()),
        }
    }

    /// Convert to a JSON Value for embedding in task output.
    pub fn to_value(&self) -> serde_json::Value {
        serde_json::to_value(self).unwrap_or_default()
    }
}
