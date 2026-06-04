"""Shared pytest fixtures for the LDP Python SDK tests."""

import pytest

from ldp_protocol.types import payload as _payload


@pytest.fixture(autouse=True)
def _isolate_payload_registry():
    """Isolate the process-global payload-codec registry between tests.

    ``register_payload_mode`` mutates module-global state (``_registered_modes``).
    Without isolation, a test that registers SEMANTIC_GRAPH would leak that
    codec into later tests (e.g. ``test_is_implemented``), making results
    order-dependent. Snapshot before each test, restore after.
    """
    saved = set(_payload._registered_modes)
    try:
        yield
    finally:
        _payload._registered_modes.clear()
        _payload._registered_modes.update(saved)
