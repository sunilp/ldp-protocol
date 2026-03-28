//! LDP capability manifest types.
//!
//! Each delegate advertises capabilities with associated quality, latency,
//! and cost metadata — richer than A2A/MCP skill listings.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// How a quality claim was established — addresses the provenance paradox.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimType {
    /// Quality scores reported by the delegate itself.
    #[default]
    SelfClaimed,
    /// Quality scores attested by a trusted third-party issuer.
    IssuerAttested,
    /// Quality scores measured by the LDP runtime during actual invocations.
    RuntimeObserved,
    /// Quality scores verified by an external benchmarking service.
    ExternallyBenchmarked,
}

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
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
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

    /// How this quality claim was established.
    #[serde(default)]
    pub claim_type: ClaimType,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_claim_type_is_self_claimed() {
        let metrics = QualityMetrics::default();
        assert_eq!(metrics.claim_type, ClaimType::SelfClaimed);
    }

    #[test]
    fn claim_type_serialization() {
        let metrics = QualityMetrics {
            claim_type: ClaimType::IssuerAttested,
            quality_score: Some(0.95),
            ..Default::default()
        };
        let json = serde_json::to_value(&metrics).unwrap();
        assert_eq!(json["claim_type"], "issuer_attested");
        let restored: QualityMetrics = serde_json::from_value(json).unwrap();
        assert_eq!(restored.claim_type, ClaimType::IssuerAttested);
    }

    #[test]
    fn all_claim_types_exist() {
        let _ = ClaimType::SelfClaimed;
        let _ = ClaimType::IssuerAttested;
        let _ = ClaimType::RuntimeObserved;
        let _ = ClaimType::ExternallyBenchmarked;
    }
}
