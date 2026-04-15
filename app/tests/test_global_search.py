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


class TestGlobalSearch:
    def test_global_search_returns_results(self, client):
        _, h = _auth(client)
        r = client.get("/api/users/global-search?q=test", headers=h)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (dict, list))

    def test_global_search_empty_query(self, client):
        _, h = _auth(client)
        r = client.get("/api/users/global-search?q=", headers=h)
        assert r.status_code in (200, 400, 422)

    def test_global_search_without_auth(self, client):
        r = client.get("/api/users/global-search?q=test")
        assert r.status_code in (200, 401, 403)


# ══════════════════════════════════════════════════════════════════════════════
# 2. MESSAGE SEARCH
# ══════════════════════════════════════════════════════════════════════════════
