"""LDP capability manifest types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QualityMetrics(BaseModel):
    """Quality, latency, and cost metrics for a capability."""

    quality_score: float | None = None
    latency_p50_ms: int | None = None
    latency_p99_ms: int | None = None
    cost_per_call_usd: float | None = None
    max_tokens: int | None = None
    supports_streaming: bool = False


class LdpCapability(BaseModel):
    """An LDP capability — a skill with quality/latency/cost metadata."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    quality: QualityMetrics | None = None
    domains: list[str] = Field(default_factory=list)
