"""Tests for LDP router."""

from ldp_protocol.router import LdpRouter, RoutingStrategy
from ldp_protocol.types import (
    LdpCapability,
    LdpIdentityCard,
    QualityMetrics,
    TrustDomain,
)


def _make_delegates() -> dict[str, LdpIdentityCard]:
    fast = LdpIdentityCard(
        delegate_id="ldp:delegate:fast",
        name="Fast Agent",
        model_family="gemini",
        model_version="gemini-flash",
        trust_domain=TrustDomain(name="research"),
        context_window=32000,
        cost_profile="low",
        endpoint="http://localhost:8091",
        capabilities=[
            LdpCapability(
                name="reasoning",
                quality=QualityMetrics(
                    quality_score=0.60,
                    cost_per_call_usd=0.001,
                    latency_p50_ms=200,
                ),
            ),
        ],
    )
    deep = LdpIdentityCard(
        delegate_id="ldp:delegate:deep",
        name="Deep Agent",
        model_family="claude",
        model_version="claude-opus",
        trust_domain=TrustDomain(name="research"),
        context_window=200000,
        cost_profile="high",
        endpoint="http://localhost:8092",
        capabilities=[
            LdpCapability(
                name="reasoning",
                quality=QualityMetrics(
                    quality_score=0.95,
                    cost_per_call_usd=0.025,
                    latency_p50_ms=3500,
                ),
            ),
        ],
    )
    external = LdpIdentityCard(
        delegate_id="ldp:delegate:external",
        name="External Agent",
        model_family="gpt",
        model_version="gpt-4o",
        trust_domain=TrustDomain(name="external"),
        context_window=128000,
        endpoint="http://localhost:8093",
        capabilities=[
            LdpCapability(
                name="reasoning",
                quality=QualityMetrics(
                    quality_score=0.88,
                    cost_per_call_usd=0.01,
                    latency_p50_ms=1000,
                ),
            ),
        ],
    )
    return {
        "http://localhost:8091": fast,
        "http://localhost:8092": deep,
        "http://localhost:8093": external,
    }


class TestRouter:
    def _make_router(self) -> LdpRouter:
        router = LdpRouter()
        router.delegates = _make_delegates()
        return router

    def test_select_by_quality(self):
        router = self._make_router()
        best = router.select("reasoning", RoutingStrategy.QUALITY)
        assert best is not None
        assert best.delegate_id == "ldp:delegate:deep"

    def test_select_by_cost(self):
        router = self._make_router()
        best = router.select("reasoning", RoutingStrategy.COST)
        assert best is not None
        assert best.delegate_id == "ldp:delegate:fast"

    def test_select_by_latency(self):
        router = self._make_router()
        best = router.select("reasoning", RoutingStrategy.LATENCY)
        assert best is not None
        assert best.delegate_id == "ldp:delegate:fast"

    def test_select_balanced(self):
        router = self._make_router()
        best = router.select("reasoning", RoutingStrategy.BALANCED)
        assert best is not None
        # Balanced should favor high quality/cost ratio — fast or external
        assert best.delegate_id in ("ldp:delegate:fast", "ldp:delegate:external")

    def test_select_with_trust_domain(self):
        router = self._make_router()
        best = router.select("reasoning", RoutingStrategy.QUALITY, trust_domain="research")
        assert best is not None
        assert best.delegate_id == "ldp:delegate:deep"
        assert best.trust_domain.name == "research"

    def test_select_nonexistent_skill(self):
        router = self._make_router()
        best = router.select("cooking", RoutingStrategy.QUALITY)
        assert best is None

    def test_select_nonexistent_trust_domain(self):
        router = self._make_router()
        best = router.select("reasoning", RoutingStrategy.QUALITY, trust_domain="secret")
        assert best is None

    def test_list_delegates(self):
        router = self._make_router()
        delegates = router.list_delegates()
        assert len(delegates) == 3

    def test_list_delegates_filtered(self):
        router = self._make_router()
        delegates = router.list_delegates(skill="reasoning")
        assert len(delegates) == 3
        delegates = router.list_delegates(skill="cooking")
        assert len(delegates) == 0
