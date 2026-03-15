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

impl Default for TrustDomain {
    fn default() -> Self {
        Self::new("default")
    }
}

impl TrustDomain {
    /// Create a new trust domain.
    pub fn new(name: impl Into<String>) -> Self {
        let name = name.into();
        assert!(!name.is_empty(), "Trust domain name must not be empty");
        Self {
            name,
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

    /// Check if two domains mutually trust each other.
    pub fn mutually_trusts(&self, peer: &TrustDomain) -> bool {
        self.trusts(&peer.name) && peer.trusts(&self.name)
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

    #[test]
    fn mutual_trust_requires_both_sides() {
        let domain_a = TrustDomain {
            name: "acme".into(),
            allow_cross_domain: true,
            trusted_peers: vec!["partner".into()],
        };
        let domain_b = TrustDomain {
            name: "partner".into(),
            allow_cross_domain: true,
            trusted_peers: vec!["acme".into()],
        };
        let domain_c = TrustDomain {
            name: "partner".into(),
            allow_cross_domain: true,
            trusted_peers: vec![],
        };
        assert!(domain_a.mutually_trusts(&domain_b));
        assert!(!domain_a.mutually_trusts(&domain_c));
    }

    #[test]
    fn same_domain_mutual_trust() {
        let domain = TrustDomain::new("acme");
        let other = TrustDomain::new("acme");
        assert!(domain.mutually_trusts(&other));
    }

    #[test]
    fn default_trust_domain() {
        let domain = TrustDomain::default();
        assert_eq!(domain.name, "default");
        assert!(!domain.allow_cross_domain);
    }

    #[test]
    #[should_panic(expected = "Trust domain name must not be empty")]
    fn empty_name_panics() {
        TrustDomain::new("");
    }
}
