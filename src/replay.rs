//! Replay detection for LDP messages.

use lru::LruCache;
use std::num::NonZeroUsize;
use std::time::Duration;

/// Guards against replayed messages using a bounded LRU cache.
///
/// Must be wrapped in `Arc<Mutex<ReplayGuard>>` for concurrent use in servers.
pub struct ReplayGuard {
    seen: LruCache<String, ()>,
    window: Duration,
}

impl ReplayGuard {
    pub fn new(capacity: usize, window_secs: u64) -> Self {
        Self {
            seen: LruCache::new(NonZeroUsize::new(capacity.max(1)).unwrap()),
            window: Duration::from_secs(window_secs),
        }
    }

    /// Check if a message should be accepted. Returns Err with reason if rejected.
    pub fn check(
        &mut self,
        message_id: &str,
        nonce: Option<&str>,
        timestamp: &str,
    ) -> Result<(), String> {
        // 1. Timestamp freshness check
        if let Ok(msg_time) = chrono::DateTime::parse_from_rfc3339(timestamp) {
            let now = chrono::Utc::now();
            let diff = (now - msg_time.with_timezone(&chrono::Utc))
                .num_seconds()
                .unsigned_abs();
            if diff > self.window.as_secs() {
                return Err(format!(
                    "Message timestamp too old: {}s > {}s window",
                    diff,
                    self.window.as_secs()
                ));
            }
        }

        // 2. Nonce deduplication (only when nonce is present)
        if let Some(nonce) = nonce {
            let key = format!("{}:{}", message_id, nonce);
            if self.seen.contains(&key) {
                return Err("Duplicate message_id + nonce pair".into());
            }
            self.seen.put(key, ());
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_fresh_message() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &ts).is_ok());
    }

    #[test]
    fn rejects_duplicate_nonce() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &ts).is_ok());
        assert!(guard.check("m1", Some("nonce1"), &ts).is_err());
    }

    #[test]
    fn accepts_different_nonce_same_message_id() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &ts).is_ok());
        assert!(guard.check("m1", Some("nonce2"), &ts).is_ok());
    }

    #[test]
    fn rejects_stale_timestamp() {
        let mut guard = ReplayGuard::new(100, 60);
        let old_ts = (chrono::Utc::now() - chrono::Duration::seconds(120)).to_rfc3339();
        assert!(guard.check("m1", Some("nonce1"), &old_ts).is_err());
    }

    #[test]
    fn skips_dedup_when_no_nonce() {
        let mut guard = ReplayGuard::new(100, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", None, &ts).is_ok());
        assert!(guard.check("m1", None, &ts).is_ok());
    }

    #[test]
    fn lru_evicts_oldest_at_capacity() {
        let mut guard = ReplayGuard::new(2, 60);
        let ts = chrono::Utc::now().to_rfc3339();
        assert!(guard.check("m1", Some("n1"), &ts).is_ok());
        assert!(guard.check("m2", Some("n2"), &ts).is_ok());
        assert!(guard.check("m3", Some("n3"), &ts).is_ok());
        // m1:n1 was evicted by m3:n3
        assert!(guard.check("m1", Some("n1"), &ts).is_ok());
        // m1:n1 re-insert evicted m2:n2, so m3:n3 is still in cache
        assert!(guard.check("m3", Some("n3"), &ts).is_err());
    }
}
