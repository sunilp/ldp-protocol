"""LDP delegation contract types."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class FailurePolicy(str, Enum):
    FAIL_CLOSED = "fail_closed"
    FAIL_OPEN = "fail_open"


class BudgetPolicy(BaseModel):
    max_tokens: int | None = None
    max_cost_usd: float | None = None


class PolicyEnvelope(BaseModel):
    failure_policy: FailurePolicy = FailurePolicy.FAIL_OPEN
    budget: BudgetPolicy | None = None
    safety_constraints: list[str] = Field(default_factory=list)
    max_delegation_depth: int | None = None


class DelegationContract(BaseModel):
    contract_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    success_criteria: list[str] = Field(default_factory=list)
    policy: PolicyEnvelope = Field(default_factory=PolicyEnvelope)
    deadline: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
