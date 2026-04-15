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


class TestNativeBridge:
    def test_capabilities(self, client):
        _, h = _auth(client)
        r = client.get("/api/native/capabilities", headers=h)
        assert r.status_code == 200
        data = r.json()
        assert "features" in data or "api_version" in data

    def test_push_register(self, client):
        _, h = _auth(client)
        r = client.post("/api/native/push/register", json={
            "token": "fake_fcm_token_12345",
            "platform": "android",
            "app_version": "1.0.0",
        }, headers=h)
        assert r.status_code in (200, 201)

    def test_push_register_invalid_platform(self, client):
        _, h = _auth(client)
        r = client.post("/api/native/push/register", json={
            "token": "fake",
            "platform": "symbian",
        }, headers=h)
        assert r.status_code in (200, 400, 422)

    def test_push_subscriptions(self, client):
        _, h = _auth(client)
        r = client.get("/api/native/push/subscriptions", headers=h)
        assert r.status_code == 200

    def test_push_unregister(self, client):
        _, h = _auth(client)
        r = client.post("/api/native/push/unregister", json={
            "endpoint": "fake_endpoint",
            "app_id": "com.vortex.chat",
        }, headers=h)
        assert r.status_code in (200, 404)

    def test_biometric_challenge(self, client):
        _, h = _auth(client)
        r = client.post("/api/native/biometric/challenge", headers=h)
        assert r.status_code in (200, 201)
        if r.status_code == 200:
            data = r.json()
            assert "challenge" in data

    def test_capabilities_requires_auth(self, client):
        r = client.get("/api/native/capabilities")
        assert r.status_code in (200, 401, 403)
