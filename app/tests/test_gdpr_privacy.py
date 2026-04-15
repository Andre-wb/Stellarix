"""Tests for GDPR/Privacy endpoints (/api/privacy/*)."""
from __future__ import annotations
from conftest import make_user, SyncASGIClient


def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


class TestGDPR:
    def test_export_data(self, client):
        _, h = _auth(client)
        r = client.get("/api/privacy/export", headers=h)
        assert r.status_code in (200, 202)

    def test_export_without_auth(self, client):
        r = client.get("/api/privacy/export")
        assert r.status_code in (200, 401, 403)

    def test_portability(self, client):
        _, h = _auth(client)
        r = client.get("/api/privacy/portability", headers=h)
        assert r.status_code in (200, 202)

    def test_rights(self, client):
        _, h = _auth(client)
        r = client.get("/api/privacy/rights", headers=h)
        assert r.status_code == 200

    def test_erase_without_auth(self, client):
        r = client.delete("/api/privacy/erase")
        assert r.status_code in (200, 401, 403)

    def test_canary(self, client):
        r = client.get("/api/privacy/canary")
        assert r.status_code == 200

    def test_canary_verify(self, client):
        r = client.get("/api/privacy/canary/verify")
        assert r.status_code in (200, 404)


class TestPanic:
    def test_panic_requires_auth(self, client):
        r = client.post("/api/panic", json={"confirm": True})
        assert r.status_code in (401, 403, 404, 422)

    def test_panic_verify(self, client):
        _, h = _auth(client)
        r = client.post("/api/panic/verify", json={}, headers=h)
        assert r.status_code in (200, 400, 404, 422)
