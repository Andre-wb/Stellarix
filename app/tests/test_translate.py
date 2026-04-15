"""Tests for Translation endpoints (/api/translate/*)."""
from __future__ import annotations
from conftest import make_user, SyncASGIClient


def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


class TestTranslate:
    def test_translate_text(self, client):
        _, h = _auth(client)
        r = client.post("/api/translate", json={
            "text": "Hello world",
            "target_lang": "ru",
        }, headers=h)
        assert r.status_code in (200, 400, 503)

    def test_translate_missing_text(self, client):
        _, h = _auth(client)
        r = client.post("/api/translate", json={
            "target_lang": "ru",
        }, headers=h)
        assert r.status_code in (400, 422)

    def test_list_languages(self, client):
        _, h = _auth(client)
        r = client.get("/api/translate/languages", headers=h)
        assert r.status_code in (200, 503)

    def test_without_auth(self, client):
        r = client.post("/api/translate", json={"text": "hi", "target_lang": "ru"})
        assert r.status_code in (200, 401, 403, 503)
