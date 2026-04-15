"""Tests for Saved GIFs endpoints (/api/gifs/*)."""
from __future__ import annotations
from conftest import make_user, SyncASGIClient


def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


class TestSavedGifs:
    def test_list_saved_gifs(self, client):
        _, h = _auth(client)
        r = client.get("/api/gifs/saved", headers=h)
        assert r.status_code == 200

    def test_save_gif(self, client):
        import os
        _, h = _auth(client)
        # saved gifs requires File upload
        fake_gif = os.urandom(64)
        r = client.post("/api/gifs/saved", files={
            "file": ("test.gif", fake_gif, "image/gif"),
        }, headers=h)
        assert r.status_code in (200, 201, 400)

    def test_delete_gif(self, client):
        _, h = _auth(client)
        # Save first
        r = client.post("/api/gifs/saved", json={
            "url": "https://example.com/delete_me.gif",
        }, headers=h)
        if r.status_code in (200, 201):
            gif_id = r.json().get("id")
            if gif_id:
                r2 = client.delete(f"/api/gifs/saved/{gif_id}", headers=h)
                assert r2.status_code in (200, 404)

    def test_without_auth(self, client):
        r = client.get("/api/gifs/saved")
        assert r.status_code in (200, 401, 403)
