//! LDP capability manifest types.
//!
//! Each delegate advertises capabilities with associated quality, latency,
//! and cost metadata — richer than A2A/MCP skill listings.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// An LDP capability — a skill with quality/latency/cost metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpCapability {
    /// Capability name (e.g. "code-review", "mathematical-reasoning").
    pub name: String,

    /// Human-readable description.
    pub description: Option<String>,

    /// Input schema (JSON Schema).
    pub input_schema: Option<Value>,

    /// Output schema (JSON Schema).
    pub output_schema: Option<Value>,

    /// Quality and performance metrics for this capability.
    pub quality: Option<QualityMetrics>,

    /// Domains this capability applies to (e.g. ["rust", "python"]).
    #[serde(default)]
    pub domains: Vec<String>,
}

/// Quality, latency, and cost metrics for a capability.
///
/// These metrics enable intelligent routing: the JamJet workflow engine
/// can select among multiple delegates based on quality-cost tradeoffs.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QualityMetrics {
    /// Self-reported quality score (0.0 – 1.0).
    pub quality_score: Option<f64>,

    /// Expected latency in milliseconds (p50).
    pub latency_p50_ms: Option<u64>,

    /// Expected latency in milliseconds (p99).
    pub latency_p99_ms: Option<u64>,

    /// Cost per invocation in USD (approximate).
    pub cost_per_call_usd: Option<f64>,

    /// Maximum tokens this capability can process per call.
    pub max_tokens: Option<u64>,

    /// Whether this capability supports streaming responses.
    pub supports_streaming: bool,
}

impl Default for QualityMetrics {
    fn default() -> Self {
        Self {
            quality_score: None,
            latency_p50_ms: None,
            latency_p99_ms: None,
            cost_per_call_usd: None,
            max_tokens: None,
            supports_streaming: false,
        }
    }
}
