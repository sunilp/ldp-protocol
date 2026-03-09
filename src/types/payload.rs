//! LDP payload mode definitions and negotiation types.
//!
//! LDP supports multiple payload modes for data exchange:
//! - Mode 0: Plain text
//! - Mode 1: Semantic frames (structured JSON)
//! - Mode 2: Embedding hints (future)
//! - Mode 3: Semantic graphs (future)
//!
//! MVP implements Modes 0 and 1 only.

use serde::{Deserialize, Serialize};
use std::fmt;

/// Payload mode for LDP message exchange.
///
/// Determines how task inputs and outputs are encoded between delegates.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PayloadMode {
    /// Mode 0: Plain text. Universal fallback — every delegate supports this.
    Text,

    /// Mode 1: Semantic frames. Structured JSON with typed fields.
    /// Maps directly to JamJet's existing `Value` payloads.
    SemanticFrame,

    /// Mode 2: Embedding hints. Text + embedding vectors for semantic routing.
    /// Not yet implemented in MVP.
    EmbeddingHints,

    /// Mode 3: Semantic graphs. RDF-like structured knowledge.
    /// Not yet implemented in MVP.
    SemanticGraph,
}

impl PayloadMode {
    /// Mode number for wire protocol.
    pub fn mode_number(&self) -> u8 {
        match self {
            PayloadMode::Text => 0,
            PayloadMode::SemanticFrame => 1,
            PayloadMode::EmbeddingHints => 2,
            PayloadMode::SemanticGraph => 3,
        }
    }

    /// Whether this mode is implemented in the current version.
    pub fn is_implemented(&self) -> bool {
        matches!(self, PayloadMode::Text | PayloadMode::SemanticFrame)
    }
}

impl fmt::Display for PayloadMode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PayloadMode::Text => write!(f, "text"),
            PayloadMode::SemanticFrame => write!(f, "semantic_frame"),
            PayloadMode::EmbeddingHints => write!(f, "embedding_hints"),
            PayloadMode::SemanticGraph => write!(f, "semantic_graph"),
        }
    }
}

/// Result of payload mode negotiation between two delegates.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NegotiatedPayload {
    /// The agreed-upon mode for this session.
    pub mode: PayloadMode,

    /// Fallback chain if the primary mode fails mid-session.
    pub fallback_chain: Vec<PayloadMode>,
}

impl Default for NegotiatedPayload {
    fn default() -> Self {
        Self {
            mode: PayloadMode::SemanticFrame,
            fallback_chain: vec![PayloadMode::Text],
        }
    }
}

/// Negotiate the best payload mode from two ordered preference lists.
///
/// Returns the highest-preference mode supported by both parties,
/// or `PayloadMode::Text` as the universal fallback.
pub fn negotiate_payload_mode(
    initiator_prefs: &[PayloadMode],
    responder_prefs: &[PayloadMode],
) -> NegotiatedPayload {
    // Find the highest-priority mode the initiator prefers that the responder also supports.
    let agreed = initiator_prefs
        .iter()
        .find(|mode| mode.is_implemented() && responder_prefs.contains(mode))
        .copied()
        .unwrap_or(PayloadMode::Text);

    // Build fallback chain: lower-priority modes both support.
    let fallback_chain: Vec<PayloadMode> = initiator_prefs
        .iter()
        .filter(|mode| {
            mode.is_implemented()
                && **mode != agreed
                && responder_prefs.contains(mode)
                && mode.mode_number() < agreed.mode_number()
        })
        .copied()
        .collect();

    NegotiatedPayload {
        mode: agreed,
        fallback_chain,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn negotiate_both_support_semantic_frame() {
        let initiator = vec![PayloadMode::SemanticFrame, PayloadMode::Text];
        let responder = vec![PayloadMode::SemanticFrame, PayloadMode::Text];
        let result = negotiate_payload_mode(&initiator, &responder);
        assert_eq!(result.mode, PayloadMode::SemanticFrame);
        assert_eq!(result.fallback_chain, vec![PayloadMode::Text]);
    }

    #[test]
    fn negotiate_falls_back_to_text() {
        let initiator = vec![PayloadMode::SemanticFrame, PayloadMode::Text];
        let responder = vec![PayloadMode::Text];
        let result = negotiate_payload_mode(&initiator, &responder);
        assert_eq!(result.mode, PayloadMode::Text);
        assert!(result.fallback_chain.is_empty());
    }

    #[test]
    fn negotiate_empty_prefs_default_to_text() {
        let result = negotiate_payload_mode(&[], &[]);
        assert_eq!(result.mode, PayloadMode::Text);
    }

    #[test]
    fn negotiate_skips_unimplemented_modes() {
        let initiator = vec![
            PayloadMode::SemanticGraph,
            PayloadMode::SemanticFrame,
            PayloadMode::Text,
        ];
        let responder = vec![PayloadMode::SemanticGraph, PayloadMode::Text];
        let result = negotiate_payload_mode(&initiator, &responder);
        // SemanticGraph is not implemented, so should fall through.
        assert_eq!(result.mode, PayloadMode::Text);
    }
}
