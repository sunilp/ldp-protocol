//! LDP HTTP client.
//!
//! Sends and receives LDP protocol messages over HTTP.
//! Each message is an `LdpEnvelope` serialized as JSON.

use crate::types::identity::LdpIdentityCard;
use crate::types::messages::LdpEnvelope;
use reqwest::Client;
use serde_json::Value;
use tracing::{debug, instrument};

/// HTTP client for LDP protocol communication.
#[derive(Debug, Clone)]
pub struct LdpClient {
    http: Client,
}

impl LdpClient {
    /// Create a new LDP client.
    pub fn new() -> Self {
        Self {
            http: Client::new(),
        }
    }

    /// Create with a custom HTTP client.
    pub fn with_http_client(http: Client) -> Self {
        Self { http }
    }

    /// Send an LDP message and receive a response.
    ///
    /// Messages are posted to `{url}/ldp/messages` as JSON.
    #[instrument(skip(self, message), fields(url = %url, msg_type = ?std::mem::discriminant(&message.body)))]
    pub async fn send_message(
        &self,
        url: &str,
        message: &LdpEnvelope,
    ) -> Result<LdpEnvelope, String> {
        let endpoint = format!("{}/ldp/messages", url.trim_end_matches('/'));

        debug!(endpoint = %endpoint, "Sending LDP message");

        let response = self
            .http
            .post(&endpoint)
            .json(message)
            .send()
            .await
            .map_err(|e| format!("LDP HTTP request failed: {e}"))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response
                .text()
                .await
                .unwrap_or_else(|_| "unable to read body".into());
            return Err(format!("LDP request failed ({}): {}", status, body));
        }

        let envelope: LdpEnvelope = response
            .json()
            .await
            .map_err(|e| format!("Failed to parse LDP response: {e}"))?;

        Ok(envelope)
    }

    /// Fetch an LDP identity card from a remote delegate.
    ///
    /// Identity cards are served at `{url}/ldp/identity`.
    #[instrument(skip(self), fields(url = %url))]
    pub async fn fetch_identity_card(&self, url: &str) -> Result<LdpIdentityCard, String> {
        let endpoint = format!("{}/ldp/identity", url.trim_end_matches('/'));

        debug!(endpoint = %endpoint, "Fetching LDP identity card");

        let response = self
            .http
            .get(&endpoint)
            .send()
            .await
            .map_err(|e| format!("Failed to fetch identity card: {e}"))?;

        if !response.status().is_success() {
            let status = response.status();
            return Err(format!("Identity card fetch failed ({})", status));
        }

        let card: LdpIdentityCard = response
            .json()
            .await
            .map_err(|e| format!("Failed to parse identity card: {e}"))?;

        Ok(card)
    }

    /// Fetch identity via .well-known convention.
    ///
    /// Tries `{url}/.well-known/ldp-identity` first, falls back to `{url}/ldp/identity`.
    pub async fn fetch_identity_wellknown(&self, url: &str) -> Result<LdpIdentityCard, String> {
        let wellknown = format!("{}/.well-known/ldp-identity", url.trim_end_matches('/'));

        match self.http.get(&wellknown).send().await {
            Ok(resp) if resp.status().is_success() => resp
                .json()
                .await
                .map_err(|e| format!("Failed to parse identity: {e}")),
            _ => self.fetch_identity_card(url).await,
        }
    }

    /// Fetch raw capabilities from a remote delegate.
    ///
    /// Capabilities are served at `{url}/ldp/capabilities`.
    #[instrument(skip(self), fields(url = %url))]
    pub async fn fetch_capabilities(&self, url: &str) -> Result<Value, String> {
        let endpoint = format!("{}/ldp/capabilities", url.trim_end_matches('/'));

        let response = self
            .http
            .get(&endpoint)
            .send()
            .await
            .map_err(|e| format!("Failed to fetch capabilities: {e}"))?;

        if !response.status().is_success() {
            let status = response.status();
            return Err(format!("Capabilities fetch failed ({})", status));
        }

        response
            .json()
            .await
            .map_err(|e| format!("Failed to parse capabilities: {e}"))
    }
}

impl Default for LdpClient {
    fn default() -> Self {
        Self::new()
    }
}
