"""
Tests for health check and metrics endpoints.
"""
import pytest


class TestHealthEndpoints:

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_contains_version(self, client):
        data = client.get("/health").json()
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_health_contains_crypto_info(self, client):
        data = client.get("/health").json()
        assert data["crypto_backend"] in ("rust", "python")
        assert "X25519" in data["key_exchange"] and "HKDF-SHA256" in data["key_exchange"]
        assert data["encryption"] == "AES-256-GCM"
        assert data["password_hash"] == "Argon2id"
        assert data["authentication"] == "JWT-HS256"

    def test_health_contains_network_info(self, client):
        data = client.get("/health").json()
        assert data["network_mode"] in ("local", "global")
        assert "active_peers" in data
        assert "ws_connections" in data

    def test_health_contains_uptime(self, client):
        data = client.get("/health").json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))

    def test_readiness_probe(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "ok"


class TestStaticEndpoints:

    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_favicon(self, client):
        resp = client.get("/favicon.ico")
        # May return 200 or 404 depending on file existence
        assert resp.status_code in (200, 404)

    def test_manifest(self, client):
        resp = client.get("/manifest.json")
        assert resp.status_code in (200, 404)

    def test_service_worker(self, client):
        resp = client.get("/service-worker.js")
        assert resp.status_code in (200, 404)


class TestExceptionHandlers:

    def test_404_returns_structured_error(self, client):
        resp = client.get("/api/nonexistent-endpoint-xyz")
        assert resp.status_code in (404, 405)
        data = resp.json()
        assert "error" in data or "detail" in data

    def test_validation_error_returns_422(self, client):
        resp = client.post("/api/authentication/register", json={"username": "x"})
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data or "detail" in data or "details" in data
