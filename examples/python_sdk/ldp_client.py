"""
LDP Client — discover delegates and submit tasks via the LDP protocol.

This example shows how to:
1. Discover a remote delegate's identity and capabilities
2. Establish a governed session with payload negotiation
3. Submit tasks and receive results with provenance
4. Route tasks based on delegate metadata (quality, cost, latency)

Usage:
    # First, start a delegate (in another terminal):
    python ldp_delegate.py

    # Then run this client:
    python ldp_client.py
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx

CLIENT_DELEGATE_ID = "ldp:delegate:orchestrator"


class LdpClient:
    """Minimal LDP client for discovering delegates and submitting tasks."""

    def __init__(self, delegate_id: str = CLIENT_DELEGATE_ID):
        self.delegate_id = delegate_id
        self.http = httpx.AsyncClient(timeout=60.0)
        self.sessions: dict[str, dict] = {}  # url -> session info

    def _envelope(self, session_id: str, to: str, body: dict) -> dict:
        return {
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "from": self.delegate_id,
            "to": to,
            "body": body,
            "payload_mode": "SemanticFrame",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": None,
        }

    # ── Discovery ─────────────────────────────────────────────────────

    async def discover(self, url: str) -> dict:
        """Fetch a delegate's identity card."""
        resp = await self.http.get(f"{url}/ldp/identity")
        resp.raise_for_status()
        return resp.json()

    # ── Session establishment ─────────────────────────────────────────

    async def establish_session(self, url: str) -> str:
        """Run the full LDP handshake and return session_id."""
        identity = await self.discover(url)
        remote_id = identity["delegate_id"]
        temp_session = str(uuid.uuid4())

        # 1. HELLO
        hello = self._envelope(temp_session, remote_id, {
            "type": "HELLO",
            "delegate_id": self.delegate_id,
            "supported_modes": ["SemanticFrame", "Text"],
        })
        resp = await self.http.post(f"{url}/ldp/messages", json=hello)
        manifest = resp.json()
        print(f"  Received: {manifest['body']['type']}")

        # 2. SESSION_PROPOSE
        propose = self._envelope(temp_session, remote_id, {
            "type": "SESSION_PROPOSE",
            "config": {
                "preferred_payload_modes": ["SemanticFrame", "Text"],
                "ttl_secs": 3600,
            },
        })
        resp = await self.http.post(f"{url}/ldp/messages", json=propose)
        accept = resp.json()
        session_id = accept["body"]["session_id"]
        mode = accept["body"]["negotiated_mode"]
        print(f"  Session established: {session_id[:8]}... (mode: {mode})")

        self.sessions[url] = {
            "session_id": session_id,
            "remote_id": remote_id,
            "mode": mode,
            "identity": identity,
        }
        return session_id

    # ── Task submission ───────────────────────────────────────────────

    async def submit_task(self, url: str, skill: str, input_data: dict) -> dict:
        """Submit a task to a delegate and return the result with provenance."""
        if url not in self.sessions:
            await self.establish_session(url)

        session = self.sessions[url]
        task_id = str(uuid.uuid4())

        submit = self._envelope(session["session_id"], session["remote_id"], {
            "type": "TASK_SUBMIT",
            "task_id": task_id,
            "skill": skill,
            "input": input_data,
        })
        resp = await self.http.post(f"{url}/ldp/messages", json=submit)
        result = resp.json()

        return {
            "task_id": task_id,
            "output": result["body"].get("output"),
            "provenance": result["body"].get("provenance"),
        }

    # ── Session close ─────────────────────────────────────────────────

    async def close_session(self, url: str) -> None:
        if url not in self.sessions:
            return
        session = self.sessions[url]
        close = self._envelope(session["session_id"], session["remote_id"], {
            "type": "SESSION_CLOSE",
            "reason": "client done",
        })
        await self.http.post(f"{url}/ldp/messages", json=close)
        del self.sessions[url]
        print(f"  Session closed")

    async def close(self) -> None:
        for url in list(self.sessions.keys()):
            await self.close_session(url)
        await self.http.aclose()


# ── Routing example ───────────────────────────────────────────────────

async def route_by_quality(delegates: list[dict], skill: str) -> dict | None:
    """Select the best delegate for a skill based on quality score."""
    best = None
    best_score = -1.0
    for d in delegates:
        for cap in d.get("capabilities", []):
            if cap["name"] == skill:
                score = cap.get("quality", {}).get("quality_score", 0)
                if score > best_score:
                    best_score = score
                    best = d
    return best


async def route_by_cost(delegates: list[dict], skill: str) -> dict | None:
    """Select the cheapest delegate for a skill."""
    best = None
    best_cost = float("inf")
    for d in delegates:
        for cap in d.get("capabilities", []):
            if cap["name"] == skill:
                cost = cap.get("quality", {}).get("cost_per_call_usd", float("inf"))
                if cost < best_cost:
                    best_cost = cost
                    best = d
    return best


# ── Main ──────────────────────────────────────────────────────────────

async def main():
    client = LdpClient()

    delegate_url = "http://localhost:8090"

    # 1. Discover
    print("1. Discovering delegate...")
    identity = await client.discover(delegate_url)
    print(f"   Name: {identity['name']}")
    print(f"   Model: {identity['model_family']} {identity['model_version']}")
    print(f"   Trust: {identity['trust_domain']['name']}")
    print(f"   Capabilities: {[c['name'] for c in identity['capabilities']]}")
    print(f"   Payload modes: {identity['supported_payload_modes']}")
    print()

    # 2. Establish session
    print("2. Establishing session...")
    session_id = await client.establish_session(delegate_url)
    print()

    # 3. Submit tasks
    print("3. Submitting reasoning task...")
    result = await client.submit_task(
        delegate_url,
        skill="reasoning",
        input_data={
            "prompt": "What are the key tradeoffs between microservices and monolithic architecture for a 5-person team?",
        },
    )
    print(f"   Output: {json.dumps(result['output'], indent=2)[:300]}...")
    print(f"   Provenance:")
    prov = result["provenance"]
    print(f"     produced_by: {prov['produced_by']}")
    print(f"     model: {prov['model_version']}")
    print(f"     confidence: {prov['confidence']}")
    print(f"     verified: {prov['verified']}")
    print()

    # 4. Submit another task (reuses session)
    print("4. Submitting summarization task (reuses session)...")
    result2 = await client.submit_task(
        delegate_url,
        skill="summarization",
        input_data={"prompt": "Summarize the key principles of LDP in 3 bullet points."},
    )
    print(f"   Output: {json.dumps(result2['output'], indent=2)[:300]}...")
    print()

    # 5. Routing example
    print("5. Routing example...")
    delegates = [identity]
    best_quality = await route_by_quality(delegates, "reasoning")
    best_cost = await route_by_cost(delegates, "reasoning")
    if best_quality:
        print(f"   Best quality for 'reasoning': {best_quality['name']}")
    if best_cost:
        print(f"   Cheapest for 'reasoning': {best_cost['name']}")
    print()

    # 6. Close
    print("6. Closing session...")
    await client.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
