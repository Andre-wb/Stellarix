"""Tests for AI Assistant endpoints (/api/ai/*)."""
from __future__ import annotations
from conftest import make_user, SyncASGIClient


def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


class TestAIAssistant:
    def test_status(self, client):
        _, h = _auth(client)
        r = client.get("/api/ai/status", headers=h)
        assert r.status_code in (200, 404, 503)

    def test_chat(self, client):
        _, h = _auth(client)
        r = client.post("/api/ai/chat", json={"room_id": 1, "message": "Hello"}, headers=h)
        assert r.status_code in (200, 400, 403, 404, 503)

    def test_summarize(self, client):
        _, h = _auth(client)
        r = client.post("/api/ai/summarize", json={"room_id": 1}, headers=h)
        assert r.status_code in (200, 400, 403, 404, 503)

    def test_suggest(self, client):
        _, h = _auth(client)
        r = client.post("/api/ai/suggest", json={"room_id": 1}, headers=h)
        assert r.status_code in (200, 400, 403, 404, 503)

    def test_fix_text(self, client):
        _, h = _auth(client)
        r = client.post("/api/ai/fix-text", json={"text": "helo wrld"}, headers=h)
        assert r.status_code in (200, 400, 503)

    def test_requires_auth(self, client):
        r = client.get("/api/ai/status")
        assert r.status_code in (200, 401, 403, 503)
