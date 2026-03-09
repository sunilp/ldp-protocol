//! LDP trust domain types.
//!
//! Trust domains partition the delegate ecosystem into security boundaries.
//! Cross-domain communication requires explicit policy approval.

use serde::{Deserialize, Serialize};

/// A trust domain — a named security boundary for delegates.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct TrustDomain {
    /// Domain name (e.g. "acme-prod", "research-sandbox").
    pub name: String,

    /// Whether cross-domain requests are allowed from this domain.
    pub allow_cross_domain: bool,

    /// Domains explicitly trusted for cross-domain communication.
    #[serde(default)]
    pub trusted_peers: Vec<String>,
}

impl TrustDomain {
    /// Create a new trust domain.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            allow_cross_domain: false,
            trusted_peers: Vec::new(),
        }
    }

    /// Check if this domain trusts a peer domain.
    pub fn trusts(&self, peer: &str) -> bool {
        if self.name == peer {
            return true; // Same domain always trusted.
        }
        self.allow_cross_domain && self.trusted_peers.contains(&peer.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn same_domain_always_trusted() {
        let domain = TrustDomain::new("acme-prod");
        assert!(domain.trusts("acme-prod"));
    }

    #[test]
    fn cross_domain_denied_by_default() {
        let domain = TrustDomain::new("acme-prod");
        assert!(!domain.trusts("external"));
    }

    #[test]
    fn cross_domain_with_explicit_peer() {
        let domain = TrustDomain {
            name: "acme-prod".into(),
            allow_cross_domain: true,
            trusted_peers: vec!["partner-corp".into()],
        };
        assert!(domain.trusts("partner-corp"));
        assert!(!domain.trusts("unknown-corp"));
    }
}
