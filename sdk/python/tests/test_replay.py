"""Tests for replay detection."""
from datetime import datetime, timedelta, timezone

from ldp_protocol.replay import ReplayGuard
from ldp_protocol.types.error import FailureCategory, LdpError


def test_security_failure_category():
    err = LdpError.security("REPLAY_DETECTED", "Duplicate nonce")
    assert err.category == FailureCategory.SECURITY
    assert err.retryable is False


def test_accepts_fresh_message():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    assert guard.check("m1", "nonce1", ts) is None


def test_rejects_duplicate_nonce():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    guard.check("m1", "nonce1", ts)
    err = guard.check("m1", "nonce1", ts)
    assert err is not None
    assert "Duplicate" in err


def test_accepts_different_nonce():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    assert guard.check("m1", "nonce1", ts) is None
    assert guard.check("m1", "nonce2", ts) is None


def test_rejects_stale_timestamp():
    guard = ReplayGuard(capacity=100, window_secs=60)
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    err = guard.check("m1", "nonce1", old_ts)
    assert err is not None
    assert "old" in err.lower() or "stale" in err.lower()


def test_skips_dedup_when_no_nonce():
    guard = ReplayGuard(capacity=100, window_secs=60)
    ts = datetime.now(timezone.utc).isoformat()
    assert guard.check("m1", None, ts) is None
    assert guard.check("m1", None, ts) is None
