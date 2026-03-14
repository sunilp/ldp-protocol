#!/usr/bin/env python3
"""
LDP Demo: Identity-Aware Routing vs Blind Routing

Shows why delegation intelligence matters with a side-by-side comparison.
No API keys needed — uses simulated delegates to demonstrate routing decisions.

Usage:
    pip install ldp-protocol
    python demo_smart_routing.py
"""

from __future__ import annotations

import asyncio
import random
import time

from ldp_protocol import (
    LdpCapability,
    LdpIdentityCard,
    LdpRouter,
    Provenance,
    QualityMetrics,
    RoutingStrategy,
    TrustDomain,
    PayloadMode,
)

# ── Simulated delegates ─────────────────────────────────────────────

DELEGATES = [
    LdpIdentityCard(
        delegate_id="ldp:delegate:fast-01",
        name="Fast Agent",
        model_family="gemini",
        model_version="gemini-2.0-flash",
        trust_domain=TrustDomain(name="research.internal"),
        context_window=32768,
        reasoning_profile="quick-lookup",
        cost_profile="low",
        endpoint="http://localhost:8091",
        capabilities=[
            LdpCapability(
                name="reasoning",
                description="Fast, lightweight reasoning for simple tasks",
                quality=QualityMetrics(
                    quality_score=0.60,
                    cost_per_call_usd=0.001,
                    latency_p50_ms=200,
                    supports_streaming=True,
                ),
            ),
        ],
        supported_payload_modes=[PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
    ),
    LdpIdentityCard(
        delegate_id="ldp:delegate:balanced-01",
        name="Balanced Agent",
        model_family="claude",
        model_version="claude-sonnet-4-6",
        trust_domain=TrustDomain(name="research.internal"),
        context_window=200000,
        reasoning_profile="analytical",
        cost_profile="medium",
        endpoint="http://localhost:8092",
        capabilities=[
            LdpCapability(
                name="reasoning",
                description="Balanced analysis and moderate reasoning",
                quality=QualityMetrics(
                    quality_score=0.82,
                    cost_per_call_usd=0.008,
                    latency_p50_ms=1200,
                    supports_streaming=True,
                ),
            ),
        ],
        supported_payload_modes=[PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
    ),
    LdpIdentityCard(
        delegate_id="ldp:delegate:deep-01",
        name="Deep Agent",
        model_family="claude",
        model_version="claude-opus-4-6",
        trust_domain=TrustDomain(name="research.internal"),
        context_window=200000,
        reasoning_profile="deep-analytical",
        cost_profile="high",
        endpoint="http://localhost:8093",
        capabilities=[
            LdpCapability(
                name="reasoning",
                description="Complex reasoning and deep analysis",
                quality=QualityMetrics(
                    quality_score=0.95,
                    cost_per_call_usd=0.025,
                    latency_p50_ms=3500,
                    supports_streaming=True,
                ),
            ),
        ],
        supported_payload_modes=[PayloadMode.SEMANTIC_FRAME, PayloadMode.TEXT],
    ),
]

# ── Tasks with varying difficulty ────────────────────────────────────

TASKS = [
    {
        "label": "easy",
        "description": "Format this JSON as a markdown table",
        "min_quality": 0.5,
    },
    {
        "label": "medium",
        "description": "Summarize the key arguments in this paragraph",
        "min_quality": 0.7,
    },
    {
        "label": "hard",
        "description": "Analyze the tradeoffs between eventual vs strong consistency",
        "min_quality": 0.9,
    },
]


def simulate_latency(delegate: LdpIdentityCard) -> int:
    """Simulate realistic latency with jitter."""
    cap = delegate.capability("reasoning")
    base = cap.quality.latency_p50_ms if cap and cap.quality else 1000
    jitter = random.randint(-int(base * 0.1), int(base * 0.1))
    return base + jitter


def blind_route(delegates: list[LdpIdentityCard], skill: str) -> LdpIdentityCard:
    """Blind routing: pick the first delegate that has the skill (no quality awareness)."""
    # Simulates what happens with skill-name-only matching:
    # often picks the most expensive one, or an arbitrary one
    for d in delegates:
        if d.capability(skill):
            return d
    raise ValueError(f"No delegate supports '{skill}'")


def smart_route(
    router: LdpRouter, task: dict, skill: str
) -> LdpIdentityCard:
    """LDP routing: match task difficulty to delegate capability."""
    min_q = task["min_quality"]

    # Find cheapest delegate that meets the quality threshold
    candidates = []
    for identity in router.delegates.values():
        cap = identity.capability(skill)
        if cap and cap.quality and cap.quality.quality_score is not None:
            if cap.quality.quality_score >= min_q:
                candidates.append(identity)

    if not candidates:
        # Fallback to best quality if nothing meets threshold
        return router.select(skill, RoutingStrategy.QUALITY)

    # Among those meeting quality threshold, pick cheapest
    candidates.sort(key=lambda d: d.cost(skill))
    return candidates[0]


async def run_demo():
    print()
    print("=" * 64)
    print("  LDP Demo: Identity-Aware Routing vs Blind Routing")
    print("=" * 64)

    # ── Discovery ────────────────────────────────────────────────
    print()
    print("Discovered 3 delegates:")
    print()

    router = LdpRouter()
    for d in DELEGATES:
        router.delegates[d.endpoint] = d
        cap = d.capability("reasoning")
        q = cap.quality if cap else None
        print(
            f"  {d.name:<16} {d.model_version:<22} "
            f"quality={q.quality_score:.2f}  "
            f"cost=${q.cost_per_call_usd:.3f}  "
            f"p50={q.latency_p50_ms}ms"
        )

    # ── Round 1: Blind Routing ───────────────────────────────────
    print()
    print("-" * 64)
    print("  Round 1: Blind Routing (skill-name only)")
    print("-" * 64)
    print()

    # Shuffle delegates so blind routing picks the "worst" order
    # (simulates arbitrary first-match behavior)
    blind_delegates = list(reversed(DELEGATES))  # deep-01 first = worst case

    blind_total_cost = 0.0
    blind_total_latency = 0
    blind_results = []

    for task in TASKS:
        selected = blind_route(blind_delegates, "reasoning")
        latency = simulate_latency(selected)
        cost = selected.cost("reasoning")

        blind_total_cost += cost
        blind_total_latency += latency
        blind_results.append(selected)

        annotation = ""
        if task["label"] == "easy":
            annotation = "  <- overkill" if selected.cost("reasoning") > 0.01 else ""
        elif task["label"] == "medium":
            annotation = "  <- expensive" if selected.cost("reasoning") > 0.01 else ""
        elif task["label"] == "hard":
            annotation = "  <- correct" if selected.quality_score("reasoning") >= 0.9 else "  <- under-powered"

        print(
            f"  Task ({task['label']:<6})  ->  {selected.name:<16} "
            f"cost=${cost:.3f}  latency={latency}ms{annotation}"
        )

    print()
    print(
        f"  Total: ${blind_total_cost:.3f}  |  {blind_total_latency:,}ms  |  "
        f"Avg quality: {sum(d.quality_score('reasoning') for d in blind_results) / len(blind_results):.2f}"
    )

    # ── Round 2: LDP Routing ─────────────────────────────────────
    print()
    print("-" * 64)
    print("  Round 2: LDP Routing (identity-aware)")
    print("-" * 64)
    print()

    ldp_total_cost = 0.0
    ldp_total_latency = 0
    ldp_results = []
    ldp_selected_list = []

    for task in TASKS:
        selected = smart_route(router, task, "reasoning")
        latency = simulate_latency(selected)
        cost = selected.cost("reasoning")

        ldp_total_cost += cost
        ldp_total_latency += latency
        ldp_results.append(selected)
        ldp_selected_list.append((task, selected, latency, cost))

        print(
            f"  Task ({task['label']:<6})  ->  {selected.name:<16} "
            f"cost=${cost:.3f}  latency={latency}ms  <- right-sized"
        )

    print()
    print(
        f"  Total: ${ldp_total_cost:.3f}  |  {ldp_total_latency:,}ms  |  "
        f"Quality matched to task complexity"
    )

    # ── Comparison ───────────────────────────────────────────────
    print()
    print("-" * 64)
    print("  Comparison")
    print("-" * 64)
    print()

    cost_saving = (1 - ldp_total_cost / blind_total_cost) * 100 if blind_total_cost else 0
    latency_saving = (1 - ldp_total_latency / blind_total_latency) * 100 if blind_total_latency else 0

    print(f"  Cost savings:    {cost_saving:.0f}% (${blind_total_cost:.3f} -> ${ldp_total_cost:.3f})")
    print(f"  Latency savings: {latency_saving:.0f}% ({blind_total_latency:,}ms -> {ldp_total_latency:,}ms)")
    print(f"  Quality:         Matched to task complexity (no overkill)")

    # ── Provenance (LDP exclusive) ───────────────────────────────
    print()
    print("-" * 64)
    print("  Provenance (LDP exclusive — blind routing can't provide this)")
    print("-" * 64)
    print()

    # Show provenance for the hard task
    hard_task, hard_delegate, hard_latency, hard_cost = ldp_selected_list[2]
    prov = Provenance.create(
        delegate_id=hard_delegate.delegate_id,
        model_version=hard_delegate.model_version,
        confidence=0.91,
        verified=True,
        payload_mode_used=PayloadMode.SEMANTIC_FRAME,
    )

    print(f"  Task 3 ({hard_task['description']}):")
    print(f"    produced_by:     {prov.produced_by}")
    print(f"    model:           {prov.model_version}")
    print(f"    confidence:      {prov.confidence}")
    print(f"    verified:        {prov.verified}")
    print(f"    payload_mode:    {prov.payload_mode_used.value} (37% fewer tokens than text)")
    print(f"    trust_domain:    {hard_delegate.trust_domain.name}")

    # ── What you get with pip install ────────────────────────────
    print()
    print("=" * 64)
    print()
    print("  Get started:")
    print("    pip install ldp-protocol")
    print()
    print("  Links:")
    print("    PyPI:   https://pypi.org/project/ldp-protocol/")
    print("    GitHub: https://github.com/sunilp/ldp-protocol")
    print("    Paper:  https://arxiv.org/abs/2603.08852")
    print()


if __name__ == "__main__":
    asyncio.run(run_demo())
