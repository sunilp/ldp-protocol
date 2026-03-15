//! End-to-end integration test: LdpAdapter ↔ LdpServer via HTTP.
//!
//! Spins up an in-process HTTP server backed by LdpServer,
//! then exercises the LdpAdapter (ProtocolAdapter) against it.

use ldp_protocol::config::LdpAdapterConfig;
use ldp_protocol::protocol::{ProtocolAdapter, TaskRequest, TaskStatus};
use ldp_protocol::server::LdpServer;
use ldp_protocol::types::messages::LdpEnvelope;
use ldp_protocol::LdpAdapter;
use serde_json::json;
use std::sync::Arc;
use tokio::net::TcpListener;

/// Spin up a minimal HTTP server wrapping an LdpServer.
///
/// Returns the base URL (e.g. "http://127.0.0.1:PORT").
async fn start_test_server(server: LdpServer) -> String {
    let server = Arc::new(server);
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    tokio::spawn(async move {
        loop {
            let (stream, _) = listener.accept().await.unwrap();
            let server = server.clone();
            tokio::spawn(async move {
                handle_connection(stream, server).await;
            });
        }
    });

    format!("http://{}", addr)
}

/// Minimal HTTP request handler — no framework dependency needed.
async fn handle_connection(stream: tokio::net::TcpStream, server: Arc<LdpServer>) {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    let mut stream = stream;
    let mut buf = vec![0u8; 65536];
    let n = stream.read(&mut buf).await.unwrap_or(0);
    if n == 0 {
        return;
    }
    let request = String::from_utf8_lossy(&buf[..n]);

    // Parse the first line for method and path.
    let first_line = request.lines().next().unwrap_or("");
    let parts: Vec<&str> = first_line.split_whitespace().collect();
    if parts.len() < 2 {
        return;
    }
    let method = parts[0];
    let path = parts[1];

    let (status, body) = match (method, path) {
        ("GET", "/ldp/identity") => {
            let identity = server.handle_identity_request();
            ("200 OK", serde_json::to_string(&identity).unwrap())
        }
        ("GET", "/ldp/capabilities") => {
            let caps = server.handle_capabilities_request();
            ("200 OK", serde_json::to_string(&caps).unwrap())
        }
        ("POST", "/ldp/messages") => {
            // Extract JSON body after the blank line.
            let body_start = request.find("\r\n\r\n").map(|i| i + 4)
                .or_else(|| request.find("\n\n").map(|i| i + 2))
                .unwrap_or(n);
            let json_body = &request[body_start..];

            match serde_json::from_str::<LdpEnvelope>(json_body) {
                Ok(envelope) => match server.handle_message(envelope).await {
                    Ok(response) => {
                        ("200 OK", serde_json::to_string(&response).unwrap())
                    }
                    Err(e) => ("500 Internal Server Error", json!({"error": e}).to_string()),
                },
                Err(e) => ("400 Bad Request", json!({"error": e.to_string()}).to_string()),
            }
        }
        _ => ("404 Not Found", json!({"error": "not found"}).to_string()),
    };

    let response = format!(
        "HTTP/1.1 {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        status,
        body.len(),
        body
    );

    let _ = stream.write_all(response.as_bytes()).await;
}

fn test_adapter() -> LdpAdapter {
    LdpAdapter::new(LdpAdapterConfig {
        delegate_id: "ldp:delegate:test-client".into(),
        trust_domain: ldp_protocol::types::trust::TrustDomain::new("test-domain"),
        ..Default::default()
    })
}

#[tokio::test]
async fn test_discover() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    let adapter = test_adapter();
    let caps = adapter.discover(&base_url).await.unwrap();

    assert_eq!(caps.name, "Echo Server");
    assert_eq!(caps.protocols, vec!["ldp"]);
    assert!(!caps.skills.is_empty());
    assert_eq!(caps.skills[0].name, "echo");
}

#[tokio::test]
async fn test_invoke_returns_handle() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    let adapter = test_adapter();
    let task = TaskRequest {
        skill: "echo".into(),
        input: json!({"message": "hello"}),
    };

    let handle = adapter.invoke(&base_url, task).await.unwrap();
    assert!(!handle.task_id.is_empty());
    assert_eq!(handle.remote_url, base_url);
}

#[tokio::test]
async fn test_invoke_and_status() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    let adapter = test_adapter();
    let task = TaskRequest {
        skill: "echo".into(),
        input: json!({"value": 42}),
    };

    let handle = adapter.invoke(&base_url, task).await.unwrap();

    // Poll status — should be completed since echo handler is synchronous.
    let status = adapter.status(&base_url, &handle.task_id).await.unwrap();

    match status {
        TaskStatus::Completed { output } => {
            // Should contain the echo output.
            assert!(output.get("echo").is_some() || output.get("result").is_some());
            // Should contain provenance.
            assert!(
                output.get("ldp_provenance").is_some(),
                "Expected provenance in output, got: {}",
                output
            );
        }
        other => panic!("Expected Completed, got: {:?}", other),
    }
}

#[tokio::test]
async fn test_session_reuse() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    let adapter = test_adapter();

    // First invocation establishes a session.
    let task1 = TaskRequest {
        skill: "echo".into(),
        input: json!({"call": 1}),
    };
    let h1 = adapter.invoke(&base_url, task1).await.unwrap();

    // Second invocation should reuse the session.
    let task2 = TaskRequest {
        skill: "echo".into(),
        input: json!({"call": 2}),
    };
    let h2 = adapter.invoke(&base_url, task2).await.unwrap();

    // Both should succeed with different task IDs.
    assert_ne!(h1.task_id, h2.task_id);

    // Session manager should have exactly 1 active session.
    assert_eq!(adapter.session_manager().active_count().await, 1);
}

#[tokio::test]
async fn test_cancel() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    let adapter = test_adapter();
    let task = TaskRequest {
        skill: "echo".into(),
        input: json!({}),
    };

    let handle = adapter.invoke(&base_url, task).await.unwrap();

    // Cancel should succeed.
    let result = adapter.cancel(&base_url, &handle.task_id).await;
    assert!(result.is_ok());
}

#[tokio::test]
async fn test_provenance_present_in_output() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    let adapter = test_adapter();
    let task = TaskRequest {
        skill: "echo".into(),
        input: json!({"data": "test"}),
    };

    let handle = adapter.invoke(&base_url, task).await.unwrap();
    let status = adapter.status(&base_url, &handle.task_id).await.unwrap();

    if let TaskStatus::Completed { output } = status {
        let prov = output.get("ldp_provenance").expect("provenance missing");
        assert_eq!(
            prov.get("produced_by").unwrap().as_str().unwrap(),
            "ldp:delegate:echo"
        );
        assert_eq!(
            prov.get("model_version").unwrap().as_str().unwrap(),
            "1.0"
        );
        assert!(prov.get("payload_mode_used").is_some());
    } else {
        panic!("Expected Completed status");
    }
}

#[tokio::test]
async fn test_trust_domain_mismatch_rejected() {
    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    // Adapter in a different trust domain that doesn't trust "test-domain".
    let adapter = LdpAdapter::new(LdpAdapterConfig {
        delegate_id: "ldp:delegate:strict-client".into(),
        trust_domain: ldp_protocol::types::trust::TrustDomain::new("production-only"),
        enforce_trust_domains: true,
        ..Default::default()
    });

    // Discovery should fail due to trust domain mismatch.
    let result = adapter.discover(&base_url).await;
    assert!(result.is_err());
    assert!(
        result.unwrap_err().contains("not trusted"),
        "Expected trust domain error"
    );
}

#[tokio::test]
async fn test_cross_domain_with_trusted_peer_succeeds() {
    use ldp_protocol::types::trust::TrustDomain;

    // Server in "partner" domain, trusts "acme".
    let server = {
        use ldp_protocol::types::identity::LdpIdentityCard;
        use ldp_protocol::types::capability::LdpCapability;
        use ldp_protocol::types::payload::PayloadMode;
        use std::collections::HashMap;
        use serde_json::json;

        let identity = LdpIdentityCard {
            delegate_id: "ldp:delegate:partner".to_string(),
            name: "Partner Server".to_string(),
            description: Some("Partner domain server".into()),
            model_family: "TestModel".into(),
            model_version: "1.0".into(),
            weights_fingerprint: None,
            trust_domain: TrustDomain {
                name: "partner".into(),
                allow_cross_domain: true,
                trusted_peers: vec!["acme".into()],
            },
            context_window: 4096,
            reasoning_profile: Some("analytical".into()),
            cost_profile: Some("low".into()),
            latency_profile: Some("p50:100ms".into()),
            jurisdiction: None,
            capabilities: vec![LdpCapability {
                name: "echo".into(),
                description: Some("Echoes input back".into()),
                input_schema: None,
                output_schema: None,
                quality: None,
                domains: vec![],
            }],
            supported_payload_modes: vec![PayloadMode::SemanticFrame, PayloadMode::Text],
            endpoint: String::new(),
            metadata: HashMap::new(),
        };

        let handler: ldp_protocol::server::TaskHandler = Arc::new(|_skill, input| {
            json!({ "echo": input })
        });

        LdpServer::new(identity, handler)
    };
    let base_url = start_test_server(server).await;

    // Adapter in "acme" domain, trusts "partner".
    let adapter = LdpAdapter::new(LdpAdapterConfig {
        delegate_id: "ldp:delegate:acme-client".into(),
        trust_domain: TrustDomain {
            name: "acme".into(),
            allow_cross_domain: true,
            trusted_peers: vec!["partner".into()],
        },
        enforce_trust_domains: true,
        ..Default::default()
    });

    // Discovery should succeed because acme trusts partner.
    let caps = adapter.discover(&base_url).await.unwrap();
    assert_eq!(caps.name, "Partner Server");
}

#[tokio::test]
async fn test_cross_domain_without_trust_fails() {
    use ldp_protocol::types::trust::TrustDomain;

    let server = LdpServer::echo_server("ldp:delegate:echo", "Echo Server");
    let base_url = start_test_server(server).await;

    // Adapter in "isolated" domain, trusts nobody.
    let adapter = LdpAdapter::new(LdpAdapterConfig {
        delegate_id: "ldp:delegate:isolated-client".into(),
        trust_domain: TrustDomain::new("isolated"),
        enforce_trust_domains: true,
        ..Default::default()
    });

    // Discovery should fail because "isolated" doesn't trust "test-domain".
    let result = adapter.discover(&base_url).await;
    assert!(result.is_err());
    assert!(
        result.unwrap_err().contains("not trusted"),
        "Expected trust domain error"
    );
}
