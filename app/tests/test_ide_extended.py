"""Tests for IDE Monitoring & Versioning endpoints (/api/ide/*)."""
from __future__ import annotations
from conftest import make_user, random_str, SyncASGIClient


def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


VALID_PID = "test_proj_" + random_str(8)


class TestIDEMonitoring:
    def test_analytics(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/analytics/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)

    def test_metrics(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/metrics/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)

    def test_queues(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/queues/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)

    def test_audit(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/audit/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)

    def test_breakers(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/breakers/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)


class TestIDEVersioning:
    def test_list_versions(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/versions/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)

    def test_save_version(self, client):
        _, h = _auth(client)
        r = client.post(f"/api/ide/save/{VALID_PID}", json={
            "code": "on /start { emit \"hello\"; }",
            "message": "initial save",
        }, headers=h)
        assert r.status_code in (200, 201, 404)

    def test_rollback_nonexistent(self, client):
        _, h = _auth(client)
        r = client.post(f"/api/ide/rollback/{VALID_PID}/999", headers=h)
        assert r.status_code in (200, 404)

    def test_dependency_graph(self, client):
        _, h = _auth(client)
        r = client.get(f"/api/ide/graph/{VALID_PID}", headers=h)
        assert r.status_code in (200, 404)
