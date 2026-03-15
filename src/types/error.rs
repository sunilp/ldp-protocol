//! LDP typed failure codes.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Category of failure.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FailureCategory {
    Identity,
    Capability,
    Policy,
    Runtime,
    Quality,
    Session,
    Transport,
}

/// Severity level of a failure.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorSeverity {
    Warning,
    Error,
    Fatal,
}

/// Structured LDP error with category, severity, and retry information.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LdpError {
    pub code: String,
    pub category: FailureCategory,
    pub message: String,
    pub severity: ErrorSeverity,
    pub retryable: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub partial_output: Option<Value>,
}

impl LdpError {
    pub fn identity(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Identity,
            message: message.into(),
            severity: ErrorSeverity::Error,
            retryable: false,
            partial_output: None,
        }
    }

    pub fn capability(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Capability,
            message: message.into(),
            severity: ErrorSeverity::Error,
            retryable: false,
            partial_output: None,
        }
    }

    pub fn policy(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Policy,
            message: message.into(),
            severity: ErrorSeverity::Fatal,
            retryable: false,
            partial_output: None,
        }
    }

    pub fn runtime(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Runtime,
            message: message.into(),
            severity: ErrorSeverity::Error,
            retryable: true,
            partial_output: None,
        }
    }

    pub fn quality(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Quality,
            message: message.into(),
            severity: ErrorSeverity::Warning,
            retryable: false,
            partial_output: None,
        }
    }

    pub fn session(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Session,
            message: message.into(),
            severity: ErrorSeverity::Error,
            retryable: true,
            partial_output: None,
        }
    }

    pub fn transport(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            category: FailureCategory::Transport,
            message: message.into(),
            severity: ErrorSeverity::Warning,
            retryable: true,
            partial_output: None,
        }
    }

    pub fn with_partial_output(mut self, output: Value) -> Self {
        self.partial_output = Some(output);
        self
    }
}

impl std::fmt::Display for LdpError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{:?}] {}: {}", self.category, self.code, self.message)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_failure() {
        let err = LdpError::identity("IDENTITY_MISMATCH", "Trust domain mismatch");
        assert_eq!(err.category, FailureCategory::Identity);
        assert!(!err.retryable);
    }

    #[test]
    fn runtime_failure_retryable() {
        let err = LdpError::runtime("TIMEOUT", "Request timed out");
        assert!(err.retryable);
    }

    #[test]
    fn error_with_partial_output() {
        let partial = serde_json::json!({"partial": "data"});
        let err = LdpError::runtime("TIMEOUT", "Timed out").with_partial_output(partial.clone());
        assert_eq!(err.partial_output, Some(partial));
    }

    #[test]
    fn serialization_roundtrip() {
        let err = LdpError::capability("SKILL_NOT_FOUND", "No such skill");
        let json = serde_json::to_value(&err).unwrap();
        let restored: LdpError = serde_json::from_value(json).unwrap();
        assert_eq!(restored.code, "SKILL_NOT_FOUND");
    }

    #[test]
    fn policy_is_fatal() {
        let err = LdpError::policy("TRUST_VIOLATION", "Not allowed");
        assert_eq!(err.severity, ErrorSeverity::Fatal);
        assert!(!err.retryable);
    }

    #[test]
    fn quality_constructor_exists() {
        let err = LdpError::quality("BELOW_THRESHOLD", "Score too low");
        assert_eq!(err.category, FailureCategory::Quality);
    }
}
