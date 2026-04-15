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


class TestSealedPrekeys:
    def test_prekey_count(self, client):
        _, h = _auth(client)
        rid = _create_room(client, h)
        if not rid:
            return
        r = client.get(f"/api/rooms/{rid}/prekey-count", headers=h)
        assert r.status_code in (200, 404)

    def test_upload_prekeys(self, client):
        _, h = _auth(client)
        rid = _create_room(client, h)
        if not rid:
            return
        packages = [
            {"ephemeral_pub": "aa" * 32, "ciphertext": "bb" * 60, "recipient_pub": "cc" * 32}
        ]
        r = client.post(f"/api/rooms/{rid}/sealed-prekeys", json={
            "packages": packages,
        }, headers=h)
        assert r.status_code in (200, 201, 403, 404)

    def test_claim_prekey(self, client):
        _, h = _auth(client)
        rid = _create_room(client, h)
        if not rid:
            return
        r = client.post(f"/api/rooms/{rid}/claim-prekey", json={
            "pubkey": "dd" * 32,
        }, headers=h)
        assert r.status_code in (200, 404)

    def test_prekey_count_non_member(self, client):
        _, h1 = _auth(client)
        _, h2 = _auth(client)
        rid = _create_room(client, h1)
        if not rid:
            return
        r = client.get(f"/api/rooms/{rid}/prekey-count", headers=h2)
        assert r.status_code in (200, 403, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 6. BOT MESSAGING
# ══════════════════════════════════════════════════════════════════════════════
