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


class TestContactSync:
    def test_sync_with_hashes(self, client):
        _, h = _auth(client)
        import hashlib
        fake_hash = hashlib.sha256(b"+1234567890").hexdigest()
        r = client.post("/api/contacts/sync", json={
            "phone_hashes": [fake_hash],
        }, headers=h)
        assert r.status_code == 200

    def test_sync_empty_list(self, client):
        _, h = _auth(client)
        r = client.post("/api/contacts/sync", json={
            "phone_hashes": [],
        }, headers=h)
        assert r.status_code in (200, 400, 422)

    def test_add_all_empty(self, client):
        _, h = _auth(client)
        r = client.post("/api/contacts/sync/add-all", json={
            "user_ids": [],
        }, headers=h)
        assert r.status_code in (200, 400, 422)

    def test_sync_requires_auth(self, client):
        r = client.post("/api/contacts/sync", json={"phone_hashes": []})
        assert r.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════════════════════
# 5. SEALED PREKEYS
# ══════════════════════════════════════════════════════════════════════════════
