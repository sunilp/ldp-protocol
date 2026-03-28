//! LDP delegation contract types.

use serde::{Deserialize, Serialize};

/// A delegation contract — bounded expectations for a task.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DelegationContract {
    pub contract_id: String,
    pub objective: String,
    pub success_criteria: Vec<String>,
    #[serde(default)]
    pub policy: PolicyEnvelope,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deadline: Option<String>,
    pub created_at: String,
}

impl DelegationContract {
    pub fn new(objective: impl Into<String>, success_criteria: Vec<String>) -> Self {
        Self {
            contract_id: uuid::Uuid::new_v4().to_string(),
            objective: objective.into(),
            success_criteria,
            policy: PolicyEnvelope::default(),
            deadline: None,
            created_at: chrono::Utc::now().to_rfc3339(),
        }
    }

    pub fn with_deadline(mut self, deadline: impl Into<String>) -> Self {
        self.deadline = Some(deadline.into());
        self
    }

    pub fn with_budget(mut self, budget: BudgetPolicy) -> Self {
        self.policy.budget = Some(budget);
        self
    }

    pub fn with_failure_policy(mut self, policy: FailurePolicy) -> Self {
        self.policy.failure_policy = policy;
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyEnvelope {
    #[serde(default)]
    pub failure_policy: FailurePolicy,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub budget: Option<BudgetPolicy>,
    #[serde(default)]
    pub safety_constraints: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_delegation_depth: Option<u32>,
}

impl Default for PolicyEnvelope {
    fn default() -> Self {
        Self {
            failure_policy: FailurePolicy::FailOpen,
            budget: None,
            safety_constraints: Vec::new(),
            max_delegation_depth: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FailurePolicy {
    FailClosed,
    FailOpen,
}

impl Default for FailurePolicy {
    fn default() -> Self {
        FailurePolicy::FailOpen
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetPolicy {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_cost_usd: Option<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contract_creation() {
        let contract =
            DelegationContract::new("Summarize the document", vec!["<=300 words".into()]);
        assert!(!contract.contract_id.is_empty());
        assert_eq!(contract.objective, "Summarize the document");
        assert!(contract.deadline.is_none());
    }

    #[test]
    fn contract_with_deadline() {
        let contract =
            DelegationContract::new("task", vec![]).with_deadline("2026-12-31T23:59:59Z");
        assert_eq!(contract.deadline.as_deref(), Some("2026-12-31T23:59:59Z"));
    }

    #[test]
    fn contract_with_budget() {
        let contract = DelegationContract::new("task", vec![]).with_budget(BudgetPolicy {
            max_tokens: Some(5000),
            max_cost_usd: Some(0.05),
        });
        assert_eq!(
            contract.policy.budget.as_ref().unwrap().max_tokens,
            Some(5000)
        );
    }

    #[test]
    fn default_failure_policy_is_fail_open() {
        let contract = DelegationContract::new("task", vec![]);
        assert_eq!(contract.policy.failure_policy, FailurePolicy::FailOpen);
    }

    #[test]
    fn serialization_roundtrip() {
        let contract = DelegationContract::new("Analyze data", vec!["accuracy > 0.9".into()])
            .with_deadline("2026-06-01T00:00:00Z")
            .with_budget(BudgetPolicy {
                max_tokens: Some(10000),
                max_cost_usd: None,
            })
            .with_failure_policy(FailurePolicy::FailClosed);
        let json = serde_json::to_value(&contract).unwrap();
        let restored: DelegationContract = serde_json::from_value(json).unwrap();
        assert_eq!(restored.objective, "Analyze data");
        assert_eq!(restored.policy.failure_policy, FailurePolicy::FailClosed);
    }

    #[test]
    fn policy_envelope_defaults() {
        let policy = PolicyEnvelope::default();
        assert_eq!(policy.failure_policy, FailurePolicy::FailOpen);
        assert!(policy.budget.is_none());
        assert!(policy.safety_constraints.is_empty());
    }
}
