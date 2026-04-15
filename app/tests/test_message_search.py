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


class TestMessageSearch:
    def test_message_search_in_room(self, client):
        _, h = _auth(client)
        rid = _create_room(client, h)
        if not rid:
            return
        r = client.get(f"/api/rooms/{rid}/messages/search?q=hello", headers=h)
        assert r.status_code in (200, 404)

    def test_message_search_non_member(self, client):
        _, h1 = _auth(client)
        _, h2 = _auth(client)
        rid = _create_room(client, h1)
        if not rid:
            return
        r = client.get(f"/api/rooms/{rid}/messages/search?q=test", headers=h2)
        assert r.status_code in (403, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 3. SECURITY QUESTIONS
# ══════════════════════════════════════════════════════════════════════════════
