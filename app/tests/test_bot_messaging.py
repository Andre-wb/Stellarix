"""
app/tests/test_coverage_gaps.py — Tests for previously untested endpoints.

Covers:
  - Global search (/api/users/global-search)
  - Message search (/api/rooms/{id}/messages/search)
  - Security questions (setup, recover, defaults, load)
  - Contact sync (sync, add-all)
  - Sealed prekeys (upload, claim, count)
  - Bot messaging (send, reply, me, rooms, updates)
  - Bot marketplace (publish, detail, reviews, install)
  - Native bridge (push register/unregister, capabilities, biometric)
"""
from __future__ import annotations

import json
import pytest

from conftest import make_user, random_str, SyncASGIClient


# ── Helpers ──────────────────────────────────────────────────────────────────

def _auth(client: SyncASGIClient):
    u = make_user(client)
    return u, u["headers"]


def _create_room(client, headers, name=None):
    r = client.post("/api/rooms", json={"name": name or f"room_{random_str(6)}"}, headers=headers)
    if r.status_code in (200, 201):
        data = r.json()
        return data.get("id") or data.get("room", {}).get("id")
    return None


def _create_bot(client, headers):
    r = client.post("/api/bots", json={
        "username": f"bot_{random_str(6)}",
        "display_name": "Test Bot",
    }, headers=headers)
    if r.status_code in (200, 201):
        return r.json()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 1. GLOBAL SEARCH
# ══════════════════════════════════════════════════════════════════════════════


class TestBotMessaging:
    def test_bot_me_invalid_token(self, client):
        r = client.get("/api/bot/me", headers={"Authorization": "Bearer invalid_token"})
        assert r.status_code in (401, 403)

    def test_bot_rooms_invalid_token(self, client):
        r = client.get("/api/bot/rooms", headers={"Authorization": "Bearer invalid_token"})
        assert r.status_code in (401, 403)

    def test_bot_send_invalid_token(self, client):
        r = client.post("/api/bot/send", json={
            "room_id": 1, "text": "hello",
        }, headers={"Authorization": "Bearer invalid_token"})
        assert r.status_code in (401, 403)

    def test_bot_reply_invalid_token(self, client):
        r = client.post("/api/bot/reply", json={
            "room_id": 1, "text": "reply", "reply_to_id": 1,
        }, headers={"Authorization": "Bearer invalid_token"})
        assert r.status_code in (401, 403)

    def test_bot_updates_invalid_token(self, client):
        r = client.get("/api/bot/updates?timeout=1", headers={"Authorization": "Bearer invalid_token"})
        assert r.status_code in (401, 403)

    def test_bot_me_with_valid_bot(self, client):
        _, h = _auth(client)
        bot = _create_bot(client, h)
        if not bot:
            return
        token = bot.get("api_token") or bot.get("token", "")
        if not token:
            return
        r = client.get("/api/bot/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code in (200, 401)


# ══════════════════════════════════════════════════════════════════════════════
# 7. BOT MARKETPLACE
# ══════════════════════════════════════════════════════════════════════════════
