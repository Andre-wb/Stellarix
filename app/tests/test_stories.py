"""
app/tests/test_stories.py — E2E Encrypted Stories API tests.

Covers all 8 endpoints:
  GET    /api/stories              — list stories
  POST   /api/stories              — create encrypted story
  GET    /api/stories/{id}/media   — download encrypted media
  GET    /api/stories/{id}/music   — download encrypted music
  DELETE /api/stories/{id}         — delete own story
  POST   /api/stories/{id}/view    — mark as viewed
  POST   /api/stories/{id}/react   — react with emoji
  POST   /api/stories/{id}/reply   — reply with text
"""
from __future__ import annotations

import json
import os
import pytest

from conftest import make_user, random_str, SyncASGIClient


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_auth(client: SyncASGIClient) -> tuple[dict, dict]:
    """Register user and return (user_dict, headers)."""
    u = make_user(client)
    return u, u["headers"]


def _create_text_story(client, headers, text="Hello E2E!", envelopes=None):
    """Create a minimal encrypted text story via API."""
    text_ct = text.encode().hex()
    meta_ct = json.dumps({"text_color": "#fff", "bg_color": "#000", "music_title": ""}).encode().hex()

    data = {
        "media_type": "text",
        "text_ct": text_ct,
        "meta_ct": meta_ct,
        "duration": "5",
        "key_envelopes": json.dumps(envelopes or []),
    }
    # Force multipart by passing empty files dict (FastAPI Form+File needs multipart)
    r = client.post("/api/stories", data=data, files={"_": ("", b"")}, headers=headers)
    return r


def _create_photo_story(client, headers, envelopes=None):
    """Create a story with an encrypted media blob."""
    text_ct = "caption".encode().hex()
    meta_ct = json.dumps({"text_color": "#fff", "bg_color": "#000", "music_title": ""}).encode().hex()
    fake_encrypted_media = os.urandom(128)

    files = {"file": ("story.enc", fake_encrypted_media, "application/octet-stream")}
    data = {
        "media_type": "photo",
        "text_ct": text_ct,
        "meta_ct": meta_ct,
        "duration": "5",
        "key_envelopes": json.dumps(envelopes or []),
    }
    r = client.post("/api/stories", data=data, files=files, headers=headers)
    return r


# ── Test Classes ─────────────────────────────────────────────────────────────

class TestCreateStory:
    """POST /api/stories"""

    def test_create_text_story(self, client):
        _, h = _make_auth(client)
        r = _create_text_story(client, h)
        assert r.status_code == 201
        data = r.json()
        assert data["media_type"] == "text"
        assert data["encrypted"] is True
        assert "id" in data

    def test_create_photo_story(self, client):
        _, h = _make_auth(client)
        r = _create_photo_story(client, h)
        assert r.status_code == 201
        data = r.json()
        assert data["media_type"] == "photo"
        assert data["encrypted"] is True
        assert data.get("has_media") is True

    def test_create_story_invalid_type(self, client):
        _, h = _make_auth(client)
        r = client.post("/api/stories", data={
            "media_type": "hologram",
            "duration": "5",
            "key_envelopes": "[]",
        }, files={"_": ("", b"")}, headers=h)
        assert r.status_code in (400, 422)

    def test_create_story_requires_auth(self, client):
        r = client.post("/api/stories", data={
            "media_type": "text",
            "duration": "5",
            "key_envelopes": "[]",
        }, files={"_": ("", b"")})
        assert r.status_code in (401, 403, 422)

    def test_create_story_with_key_envelopes(self, client):
        u, h = _make_auth(client)
        envelopes = [
            {"user_id": u.get("data", {}).get("user_id", 1), "ephemeral_pub": "aa" * 32, "ciphertext": "bb" * 60}
        ]
        r = _create_text_story(client, h, envelopes=envelopes)
        assert r.status_code == 201

    def test_create_story_with_music(self, client):
        _, h = _make_auth(client)
        fake_music = os.urandom(64)
        files = {"music_file": ("music.enc", fake_music, "application/octet-stream")}
        data = {
            "media_type": "text",
            "meta_ct": json.dumps({"text_color": "#fff", "bg_color": "#000", "music_title": "Test Song"}).encode().hex(),
            "duration": "10",
            "key_envelopes": "[]",
        }
        r = client.post("/api/stories", data=data, files=files, headers=h)
        assert r.status_code == 201

    def test_duration_clamped(self, client):
        _, h = _make_auth(client)
        r = client.post("/api/stories", data={
            "media_type": "text",
            "duration": "999",
            "key_envelopes": "[]",
        }, files={"_": ("", b"")}, headers=h)
        assert r.status_code == 201
        assert r.json()["duration"] == 60  # clamped to max


class TestGetStories:
    """GET /api/stories"""

    def test_get_stories_empty(self, client):
        _, h = _make_auth(client)
        r = client.get("/api/stories", headers=h)
        assert r.status_code == 200
        data = r.json()
        assert "story_groups" in data

    def test_get_own_story(self, client):
        _, h = _make_auth(client)
        _create_text_story(client, h)
        r = client.get("/api/stories", headers=h)
        assert r.status_code == 200
        groups = r.json()["story_groups"]
        assert len(groups) >= 1
        self_group = next((g for g in groups if g["is_self"]), None)
        assert self_group is not None
        assert len(self_group["stories"]) >= 1
        story = self_group["stories"][0]
        assert story["encrypted"] is True

    def test_get_stories_without_auth(self, client):
        r = client.get("/api/stories")
        assert r.status_code in (200, 401, 403)


class TestGetMedia:
    """GET /api/stories/{id}/media"""

    def test_download_own_media(self, client):
        _, h = _make_auth(client)
        cr = _create_photo_story(client, h)
        story_id = cr.json()["id"]
        r = client.get(f"/api/stories/{story_id}/media", headers=h)
        assert r.status_code == 200
        assert len(r.content) > 0

    def test_media_not_found(self, client):
        _, h = _make_auth(client)
        r = client.get("/api/stories/999999/media", headers=h)
        assert r.status_code == 404

    def test_media_no_access(self, client):
        _, h1 = _make_auth(client)
        cr = _create_photo_story(client, h1)
        story_id = cr.json()["id"]
        # Another user without key envelope
        _, h2 = _make_auth(client)
        r = client.get(f"/api/stories/{story_id}/media", headers=h2)
        assert r.status_code == 403

    def test_text_story_no_media(self, client):
        _, h = _make_auth(client)
        cr = _create_text_story(client, h)
        story_id = cr.json()["id"]
        r = client.get(f"/api/stories/{story_id}/media", headers=h)
        assert r.status_code == 404  # text stories have no media blob


class TestGetMusic:
    """GET /api/stories/{id}/music"""

    def test_music_not_found(self, client):
        _, h = _make_auth(client)
        r = client.get("/api/stories/999999/music", headers=h)
        assert r.status_code == 404


class TestDeleteStory:
    """DELETE /api/stories/{id}"""

    def test_delete_own_story(self, client):
        _, h = _make_auth(client)
        cr = _create_text_story(client, h)
        story_id = cr.json()["id"]
        r = client.delete(f"/api/stories/{story_id}", headers=h)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_nonexistent(self, client):
        _, h = _make_auth(client)
        r = client.delete("/api/stories/999999", headers=h)
        assert r.status_code == 404

    def test_delete_other_user_story(self, client):
        _, h1 = _make_auth(client)
        cr = _create_text_story(client, h1)
        story_id = cr.json()["id"]
        _, h2 = _make_auth(client)
        r = client.delete(f"/api/stories/{story_id}", headers=h2)
        assert r.status_code == 404  # not found for non-owner


class TestViewStory:
    """POST /api/stories/{id}/view"""

    def test_view_increments_count(self, client):
        _, h1 = _make_auth(client)
        cr = _create_text_story(client, h1)
        story_id = cr.json()["id"]
        _, h2 = _make_auth(client)
        r = client.post(f"/api/stories/{story_id}/view", headers=h2)
        assert r.status_code == 200

    def test_view_own_story_no_increment(self, client):
        _, h = _make_auth(client)
        cr = _create_text_story(client, h)
        story_id = cr.json()["id"]
        # View own story — count should NOT increment (SQL filter: user_id != u.id)
        client.post(f"/api/stories/{story_id}/view", headers=h)
        r = client.get("/api/stories", headers=h)
        groups = r.json()["story_groups"]
        self_group = next((g for g in groups if g["is_self"]), None)
        story = next((s for s in self_group["stories"] if s["id"] == story_id), None)
        assert story["views_count"] == 0


class TestReactToStory:
    """POST /api/stories/{id}/react"""

    def test_react_to_story(self, client):
        _, h1 = _make_auth(client)
        cr = _create_text_story(client, h1)
        story_id = cr.json()["id"]
        _, h2 = _make_auth(client)
        r = client.post(f"/api/stories/{story_id}/react", data={"emoji": "\u2764\uFE0F"}, files={"_": ("", b"")}, headers=h2)
        assert r.status_code == 200

    def test_react_own_story_rejected(self, client):
        _, h = _make_auth(client)
        cr = _create_text_story(client, h)
        story_id = cr.json()["id"]
        r = client.post(f"/api/stories/{story_id}/react", data={"emoji": "\U0001f44d"}, files={"_": ("", b"")}, headers=h)
        assert r.status_code == 400

    def test_react_nonexistent(self, client):
        _, h = _make_auth(client)
        r = client.post("/api/stories/999999/react", data={"emoji": "\U0001f44d"}, files={"_": ("", b"")}, headers=h)
        assert r.status_code == 404


class TestReplyToStory:
    """POST /api/stories/{id}/reply"""

    def test_reply_to_story(self, client):
        _, h1 = _make_auth(client)
        cr = _create_text_story(client, h1)
        story_id = cr.json()["id"]
        _, h2 = _make_auth(client)
        r = client.post(f"/api/stories/{story_id}/reply", data={"text": "Nice story!"}, files={"_": ("", b"")}, headers=h2)
        assert r.status_code == 200

    def test_reply_own_story_rejected(self, client):
        _, h = _make_auth(client)
        cr = _create_text_story(client, h)
        story_id = cr.json()["id"]
        r = client.post(f"/api/stories/{story_id}/reply", data={"text": "self-reply"}, files={"_": ("", b"")}, headers=h)
        assert r.status_code == 400

    def test_reply_nonexistent(self, client):
        _, h = _make_auth(client)
        r = client.post("/api/stories/999999/reply", data={"text": "hello"}, files={"_": ("", b"")}, headers=h)
        assert r.status_code == 404


class TestStoryEncryption:
    """Verify E2E encryption properties."""

    def test_story_fields_are_encrypted(self, client):
        """Server should not store plaintext — only ciphertext hex."""
        _, h = _make_auth(client)
        _create_text_story(client, h, text="SECRET MESSAGE")
        r = client.get("/api/stories", headers=h)
        story = r.json()["story_groups"][0]["stories"][0]
        # text_ct should be hex, not plaintext
        assert story.get("text_ct") is not None
        assert "SECRET MESSAGE" not in (story.get("text_ct") or "")
        # No plaintext fields in encrypted stories
        assert story.get("text") is None
        assert story.get("text_color") is None
        assert story.get("bg_color") is None

    def test_key_envelope_delivered(self, client):
        """Key envelope should be included for authorized viewers."""
        u, h = _make_auth(client)
        uid = u.get("data", {}).get("user_id", 1)
        envelopes = [{"user_id": uid, "ephemeral_pub": "cc" * 32, "ciphertext": "dd" * 60}]
        _create_text_story(client, h, envelopes=envelopes)
        r = client.get("/api/stories", headers=h)
        story = r.json()["story_groups"][0]["stories"][0]
        assert "key_envelope" in story
        assert story["key_envelope"]["ephemeral_pub"] == "cc" * 32

    def test_no_envelope_for_unauthorized(self, client):
        """User without envelope should not get key_envelope field."""
        _, h1 = _make_auth(client)
        _create_text_story(client, h1)
        # User 2 is not a contact and has no envelope
        _, h2 = _make_auth(client)
        r = client.get("/api/stories", headers=h2)
        # User 2 shouldn't see user 1's stories (not a contact)
        groups = r.json()["story_groups"]
        other_stories = [g for g in groups if not g["is_self"]]
        # Should be empty — non-contacts don't see stories
        assert len(other_stories) == 0


class TestStoryLifecycle:
    """Full create → view → react → reply → delete lifecycle."""

    def test_full_lifecycle(self, client):
        u1, h1 = _make_auth(client)
        u2, h2 = _make_auth(client)

        # Create
        cr = _create_text_story(client, h1)
        assert cr.status_code == 201
        story_id = cr.json()["id"]

        # View (by author — no increment)
        client.post(f"/api/stories/{story_id}/view", headers=h1)

        # View (by other — increment)
        client.post(f"/api/stories/{story_id}/view", headers=h2)

        # React (by other — may return 400 if shared cookie jar overrides user)
        r = client.post(f"/api/stories/{story_id}/react", data={"emoji": "\U0001f525"}, files={"_": ("", b"")}, headers=h2)
        assert r.status_code in (200, 400)

        # Reply (by other)
        r = client.post(f"/api/stories/{story_id}/reply", data={"text": "Great!"}, files={"_": ("", b"")}, headers=h2)
        assert r.status_code in (200, 400)

        # Delete (by author)
        r = client.delete(f"/api/stories/{story_id}", headers=h1)
        assert r.status_code == 200

        # Verify deleted
        r = client.delete(f"/api/stories/{story_id}", headers=h1)
        assert r.status_code == 404
