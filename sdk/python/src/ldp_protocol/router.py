"""LDP router — discover multiple delegates and route tasks intelligently."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ldp_protocol.client import LdpClient
from ldp_protocol.types.identity import LdpIdentityCard
from ldp_protocol.types.trust import TrustDomain


class RoutingStrategy(str, Enum):
    """Strategy for selecting a delegate."""

    QUALITY = "quality"
    COST = "cost"
    LATENCY = "latency"
    BALANCED = "balanced"


class LdpRouter:
    """Multi-delegate router with identity-aware routing.

    Discovers delegates and routes tasks based on quality, cost, latency,
    or a balanced score — the core capability that LDP adds on top of
    skill-name-only protocols.

    Usage:
        router = LdpRouter()
        await router.discover_delegates([
            "http://fast-model:8091",
            "http://deep-model:8092",
        ])

        result = await router.route_and_submit(
            skill="reasoning",
            input_data={"prompt": "Analyze..."},
            strategy=RoutingStrategy.QUALITY,
        )
    """

    def __init__(
        self,
        client: LdpClient | None = None,
        delegate_id: str = "ldp:router:default",
        trust_domain: TrustDomain | None = None,
        enforce_trust_domains: bool = True,
    ):
        self._client = client
        self._own_client = client is None
        self._delegate_id = delegate_id
        self._trust_domain = trust_domain
        self._enforce_trust_domains = enforce_trust_domains
        self.delegates: dict[str, LdpIdentityCard] = {}

    async def __aenter__(self) -> LdpRouter:
        if self._client is None:
            self._client = LdpClient(
                delegate_id=self._delegate_id,
                trust_domain=self._trust_domain,
                enforce_trust_domains=self._enforce_trust_domains,
            )
        return self

    async def __aexit__(self, *args) -> None:
        if self._own_client and self._client:
            await self._client.close()

    @property
    def client(self) -> LdpClient:
        if self._client is None:
            self._client = LdpClient(
                delegate_id=self._delegate_id,
                trust_domain=self._trust_domain,
                enforce_trust_domains=self._enforce_trust_domains,
            )
        return self._client

    async def discover_delegates(self, urls: list[str]) -> list[LdpIdentityCard]:
        """Discover delegates from a list of URLs.

        Returns only the delegates that responded successfully.
        """
        discovered = []
        for url in urls:
            try:
                identity = await self.client.discover(url)
                identity.endpoint = url
                self.delegates[url] = identity
                discovered.append(identity)
            except Exception:
                pass
        return discovered

    def select(
        self,
        skill: str,
        strategy: RoutingStrategy = RoutingStrategy.QUALITY,
        trust_domain: str | None = None,
    ) -> LdpIdentityCard | None:
        """Select the best delegate for a skill using the given strategy.

        Args:
            skill: The skill to route.
            strategy: Routing strategy (quality, cost, latency, balanced).
            trust_domain: If set, only consider delegates in this domain.

        Returns:
            The best matching delegate, or None if no delegates support the skill.
        """
        candidates = []
        for identity in self.delegates.values():
            cap = identity.capability(skill)
            if cap is None:
                continue
            if trust_domain and identity.trust_domain.name != trust_domain:
                continue
            candidates.append(identity)

        if not candidates:
            return None

        if strategy == RoutingStrategy.QUALITY:
            candidates.sort(key=lambda d: -d.quality_score(skill))
        elif strategy == RoutingStrategy.COST:
            candidates.sort(key=lambda d: d.cost(skill))
        elif strategy == RoutingStrategy.LATENCY:
            candidates.sort(key=lambda d: d.latency(skill))
        elif strategy == RoutingStrategy.BALANCED:
            def balanced_score(d: LdpIdentityCard) -> float:
                q = d.quality_score(skill)
                c = d.cost(skill)
                lat = d.latency(skill)
                return q / (c * lat + 1e-9)
            candidates.sort(key=balanced_score, reverse=True)

        return candidates[0]

    async def route_and_submit(
        self,
        *,
        skill: str,
        input_data: Any,
        strategy: RoutingStrategy = RoutingStrategy.QUALITY,
        trust_domain: str | None = None,
    ) -> dict[str, Any]:
        """Select the best delegate and submit a task.

        Combines `select()` and `submit_task()` in one call.

        Args:
            skill: Skill to invoke.
            input_data: Input data for the task.
            strategy: Routing strategy.
            trust_domain: Optional trust domain filter.

        Returns:
            Dict with 'output', 'provenance', and 'routed_to' keys.

        Raises:
            ValueError: If no delegate supports the skill.
        """
        delegate = self.select(skill, strategy, trust_domain)
        if delegate is None:
            raise ValueError(
                f"No delegate supports skill '{skill}' "
                f"(strategy={strategy.value}, trust_domain={trust_domain})"
            )

        result = await self.client.submit_task(
            delegate.endpoint,
            skill=skill,
            input_data=input_data,
        )
        result["routed_to"] = {
            "delegate_id": delegate.delegate_id,
            "name": delegate.name,
            "model_family": delegate.model_family,
            "endpoint": delegate.endpoint,
            "strategy": strategy.value,
        }
        return result

    def list_delegates(self, skill: str | None = None) -> list[dict[str, Any]]:
        """List all discovered delegates, optionally filtered by skill."""
        result = []
        for url, identity in self.delegates.items():
            if skill and identity.capability(skill) is None:
                continue
            result.append({
                "delegate_id": identity.delegate_id,
                "name": identity.name,
                "model_family": identity.model_family,
                "model_version": identity.model_version,
                "endpoint": url,
                "trust_domain": identity.trust_domain.name,
                "capabilities": [c.name for c in identity.capabilities],
                "quality_scores": {
                    c.name: c.quality.quality_score
                    for c in identity.capabilities
                    if c.quality and c.quality.quality_score is not None
                },
            })
        return result
