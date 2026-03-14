"""
Multi-delegate routing — discover multiple LDP delegates and route tasks
based on identity metadata (quality, cost, latency, trust domain).

This demonstrates LDP's key advantage over skill-name-only protocols:
the router has rich metadata to make intelligent delegation decisions.

Usage:
    # Start two delegates (in separate terminals):
    DELEGATE_ID=ldp:delegate:fast-01 MODEL=gemini PORT=8091 python ldp_delegate.py
    DELEGATE_ID=ldp:delegate:deep-01 MODEL=claude PORT=8092 python ldp_delegate.py

    # Run the router:
    python multi_delegate_routing.py
"""

from __future__ import annotations

import asyncio
import httpx


async def discover(url: str) -> dict | None:
    """Discover a delegate's identity card."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{url}/ldp/identity")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def find_capability(identity: dict, skill: str) -> dict | None:
    """Find a specific capability in an identity card."""
    for cap in identity.get("capabilities", []):
        if cap["name"] == skill:
            return cap
    return None


def route_task(delegates: list[dict], skill: str, strategy: str = "quality") -> dict | None:
    """
    Route a task to the best delegate based on strategy.

    Strategies:
        quality  — highest quality_score
        cost     — lowest cost_per_call_usd
        latency  — lowest latency_p50_ms
        balanced — quality / (cost * latency) score
    """
    candidates = []
    for d in delegates:
        cap = find_capability(d, skill)
        if cap is None:
            continue
        q = cap.get("quality", {})
        candidates.append({
            "identity": d,
            "capability": cap,
            "quality_score": q.get("quality_score", 0),
            "cost": q.get("cost_per_call_usd", float("inf")),
            "latency": q.get("latency_p50_ms", float("inf")),
        })

    if not candidates:
        return None

    if strategy == "quality":
        candidates.sort(key=lambda c: -c["quality_score"])
    elif strategy == "cost":
        candidates.sort(key=lambda c: c["cost"])
    elif strategy == "latency":
        candidates.sort(key=lambda c: c["latency"])
    elif strategy == "balanced":
        for c in candidates:
            # Normalize: higher is better
            c["score"] = c["quality_score"] / (c["cost"] * c["latency"] + 1e-9)
        candidates.sort(key=lambda c: -c["score"])

    return candidates[0]["identity"]


async def main():
    # Discover delegates from known endpoints
    endpoints = [
        "http://localhost:8090",
        "http://localhost:8091",
        "http://localhost:8092",
    ]

    print("Discovering delegates...")
    delegates = []
    for url in endpoints:
        identity = await discover(url)
        if identity:
            delegates.append(identity)
            cap_names = [c["name"] for c in identity.get("capabilities", [])]
            print(f"  Found: {identity['name']} ({identity['delegate_id']})")
            print(f"    Model: {identity['model_family']} {identity['model_version']}")
            print(f"    Caps: {cap_names}")
            print(f"    Cost: {identity.get('cost_profile', 'unknown')}")
        else:
            print(f"  {url}: not reachable")

    if not delegates:
        print("\nNo delegates found. Start at least one delegate first.")
        return

    print(f"\n{len(delegates)} delegate(s) available\n")

    # Route tasks with different strategies
    skill = "reasoning"
    for strategy in ["quality", "cost", "latency", "balanced"]:
        best = route_task(delegates, skill, strategy)
        if best:
            cap = find_capability(best, skill)
            q = cap.get("quality", {}) if cap else {}
            print(f"  [{strategy:>8}] → {best['name']}"
                  f" (quality={q.get('quality_score', '?')}"
                  f", cost=${q.get('cost_per_call_usd', '?')}"
                  f", p50={q.get('latency_p50_ms', '?')}ms)")
        else:
            print(f"  [{strategy:>8}] → no delegate supports '{skill}'")

    # Trust domain filtering
    print("\nTrust domain filtering:")
    my_domain = "research.internal"
    trusted = [d for d in delegates if d.get("trust_domain", {}).get("name") == my_domain]
    untrusted = [d for d in delegates if d.get("trust_domain", {}).get("name") != my_domain]
    print(f"  Same domain ({my_domain}): {len(trusted)} delegate(s)")
    print(f"  Cross domain: {len(untrusted)} delegate(s)")


if __name__ == "__main__":
    asyncio.run(main())
