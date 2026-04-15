"""Tests for BMP Push Proxy endpoints (/api/push-proxy/*)."""
from __future__ import annotations
from conftest import make_user, SyncASGIClient


def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


class TestBMPPush:
    def test_register(self, client):
        r = client.post("/api/push-proxy/register", json={
            "categories": [0, 1, 2],
            "token": "fake_push_token_1234567890",
            "endpoint": "https://push.example.com/send/abc123xyz",
        })
        assert r.status_code in (200, 201, 403)

    def test_unregister(self, client):
        _, h = _auth(client)
        r = client.post("/api/push-proxy/unregister", json={
            "endpoint": "https://push.example.com/send/abc123",
        }, headers=h)
        assert r.status_code in (200, 404)

    def test_stats(self, client):
        _, h = _auth(client)
        r = client.get("/api/push-proxy/stats", headers=h)
        assert r.status_code in (200, 403)

    def test_wake(self, client):
        r = client.post("/api/push-proxy/wake", json={
            "category": 42,
        })
        assert r.status_code in (200, 403)
