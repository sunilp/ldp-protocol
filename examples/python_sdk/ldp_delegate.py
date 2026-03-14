"""
LDP Delegate — serve an LLM as an LDP-compatible delegate.

This example creates a delegate that:
1. Publishes an LDP identity card at GET /ldp/identity
2. Accepts LDP messages at POST /ldp/messages
3. Handles the full session lifecycle (HELLO → SESSION → TASK → CLOSE)
4. Attaches provenance to every response

Usage:
    pip install httpx uvicorn starlette
    python ldp_delegate.py

Then discover it:
    curl http://localhost:8090/ldp/identity | python -m json.tool
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# ── Configuration ─────────────────────────────────────────────────────

DELEGATE_ID = "ldp:delegate:analyst-01"
DELEGATE_NAME = "Research Analyst"
MODEL_FAMILY = "claude"
MODEL_VERSION = "claude-sonnet-4-6"
TRUST_DOMAIN = "research.internal"
PORT = 8090

# ── Identity Card ─────────────────────────────────────────────────────

IDENTITY_CARD = {
    "delegate_id": DELEGATE_ID,
    "name": DELEGATE_NAME,
    "description": "Analytical reasoning specialist for research tasks",
    "model_family": MODEL_FAMILY,
    "model_version": MODEL_VERSION,
    "trust_domain": {
        "name": TRUST_DOMAIN,
        "allow_cross_domain": False,
        "trusted_peers": [],
    },
    "context_window": 200000,
    "reasoning_profile": "deep-analytical",
    "cost_profile": "medium",
    "latency_profile": "p50:3000ms",
    "capabilities": [
        {
            "name": "reasoning",
            "description": "Complex multi-step reasoning and analysis",
            "quality": {
                "quality_score": 0.88,
                "latency_p50_ms": 3000,
                "latency_p99_ms": 12000,
                "cost_per_call_usd": 0.015,
                "supports_streaming": True,
            },
            "domains": ["research", "analysis", "strategy"],
        },
        {
            "name": "summarization",
            "description": "Concise summarization of complex documents",
            "quality": {
                "quality_score": 0.92,
                "latency_p50_ms": 2000,
                "latency_p99_ms": 6000,
                "cost_per_call_usd": 0.008,
                "supports_streaming": True,
            },
            "domains": ["research", "writing"],
        },
    ],
    "supported_payload_modes": ["SemanticFrame", "Text"],
    "endpoint": f"ldp://localhost:{PORT}",
    "metadata": {},
}

# ── In-memory state ───────────────────────────────────────────────────

sessions: dict[str, dict] = {}
tasks: dict[str, dict] = {}

# ── LLM call (replace with your preferred provider) ──────────────────

async def call_llm(prompt: str) -> str:
    """Call an LLM. Replace this with Anthropic/OpenAI/local model."""
    try:
        import httpx

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-6-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                data = resp.json()
                return data["content"][0]["text"]
    except Exception:
        pass

    # Fallback: echo response for testing without API keys
    return f"[echo] Received task: {prompt[:200]}"


# ── Message handlers ──────────────────────────────────────────────────

def make_envelope(session_id: str, to: str, body: dict) -> dict:
    return {
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "from": DELEGATE_ID,
        "to": to,
        "body": body,
        "payload_mode": "SemanticFrame",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provenance": None,
    }


async def handle_hello(envelope: dict) -> dict:
    return make_envelope(
        envelope["session_id"],
        envelope["from"],
        {
            "type": "CAPABILITY_MANIFEST",
            "capabilities": IDENTITY_CARD["capabilities"],
        },
    )


async def handle_session_propose(envelope: dict) -> dict:
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "remote": envelope["from"],
        "state": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return make_envelope(
        session_id,
        envelope["from"],
        {
            "type": "SESSION_ACCEPT",
            "session_id": session_id,
            "negotiated_mode": "SemanticFrame",
        },
    )


async def handle_task_submit(envelope: dict) -> dict:
    body = envelope["body"]
    task_id = body["task_id"]
    skill = body["skill"]
    task_input = body["input"]

    # Extract prompt from input
    if isinstance(task_input, dict):
        prompt = task_input.get("prompt", task_input.get("text", json.dumps(task_input)))
    else:
        prompt = str(task_input)

    # Call LLM
    output = await call_llm(f"[{skill}] {prompt}")

    tasks[task_id] = {"status": "completed", "output": output}

    return make_envelope(
        envelope["session_id"],
        envelope["from"],
        {
            "type": "TASK_RESULT",
            "task_id": task_id,
            "output": {"text": output},
            "provenance": {
                "produced_by": DELEGATE_ID,
                "model_version": MODEL_VERSION,
                "payload_mode_used": "SemanticFrame",
                "confidence": 0.85,
                "verified": False,
                "session_id": envelope["session_id"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        },
    )


async def handle_session_close(envelope: dict) -> dict:
    sid = envelope["session_id"]
    if sid in sessions:
        sessions[sid]["state"] = "closed"
    return make_envelope(
        sid,
        envelope["from"],
        {"type": "SESSION_CLOSE", "reason": "acknowledged"},
    )


MESSAGE_HANDLERS = {
    "HELLO": handle_hello,
    "SESSION_PROPOSE": handle_session_propose,
    "TASK_SUBMIT": handle_task_submit,
    "SESSION_CLOSE": handle_session_close,
}

# ── HTTP endpoints ────────────────────────────────────────────────────

async def identity_endpoint(request: Request) -> JSONResponse:
    """GET /ldp/identity — serve the delegate's identity card."""
    return JSONResponse(IDENTITY_CARD)


async def capabilities_endpoint(request: Request) -> JSONResponse:
    """GET /ldp/capabilities — serve capability manifest."""
    return JSONResponse({"capabilities": IDENTITY_CARD["capabilities"]})


async def messages_endpoint(request: Request) -> JSONResponse:
    """POST /ldp/messages — handle LDP protocol messages."""
    envelope = await request.json()
    msg_type = envelope.get("body", {}).get("type", "")

    handler = MESSAGE_HANDLERS.get(msg_type)
    if handler is None:
        return JSONResponse(
            {"error": f"Unknown message type: {msg_type}"}, status_code=400
        )

    response = await handler(envelope)
    return JSONResponse(response)


app = Starlette(
    routes=[
        Route("/ldp/identity", identity_endpoint, methods=["GET"]),
        Route("/ldp/capabilities", capabilities_endpoint, methods=["GET"]),
        Route("/ldp/messages", messages_endpoint, methods=["POST"]),
    ],
)

if __name__ == "__main__":
    import uvicorn

    print(f"Starting LDP delegate: {DELEGATE_NAME} ({DELEGATE_ID})")
    print(f"Identity: http://localhost:{PORT}/ldp/identity")
    print(f"Messages: http://localhost:{PORT}/ldp/messages")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
