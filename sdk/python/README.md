# LDP Protocol — Python SDK

Identity-aware communication protocol for multi-agent LLM systems.

```bash
pip install ldp-protocol
```

## Quick Start

### Create a delegate

```python
from ldp_protocol import LdpDelegate, LdpCapability, QualityMetrics

class MyDelegate(LdpDelegate):
    async def handle_task(self, skill, input_data, task_id):
        return {"answer": "42"}, 0.95

delegate = MyDelegate(
    delegate_id="ldp:delegate:my-agent",
    name="My Agent",
    model_family="claude",
    model_version="claude-sonnet-4-6",
    capabilities=[
        LdpCapability(
            name="reasoning",
            quality=QualityMetrics(quality_score=0.85, cost_per_call_usd=0.01),
        ),
    ],
)
delegate.run(port=8090)  # requires: pip install ldp-protocol[server]
```

### Discover and invoke

```python
from ldp_protocol import LdpClient

async with LdpClient() as client:
    identity = await client.discover("http://localhost:8090")
    print(f"Found: {identity.name} ({identity.model_family})")

    result = await client.submit_task(
        "http://localhost:8090",
        skill="reasoning",
        input_data={"prompt": "Analyze the tradeoffs..."},
    )
    print(f"Output: {result['output']}")
    print(f"Provenance: {result['provenance']}")
```

### Multi-delegate routing

```python
from ldp_protocol import LdpRouter, RoutingStrategy

async with LdpRouter() as router:
    await router.discover_delegates([
        "http://fast-model:8091",
        "http://deep-model:8092",
    ])

    # Route by quality, cost, latency, or balanced score
    result = await router.route_and_submit(
        skill="reasoning",
        input_data={"prompt": "Complex analysis..."},
        strategy=RoutingStrategy.QUALITY,
    )
    print(f"Routed to: {result['routed_to']['name']}")
```

## Links

- [Protocol specification](https://github.com/sunilp/ldp-protocol)
- [Research paper](https://arxiv.org/abs/2603.08852)
- [Rust reference implementation](https://github.com/sunilp/ldp-protocol)
