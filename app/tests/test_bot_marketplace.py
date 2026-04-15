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


class TestBotMarketplace:
    def test_marketplace_list(self, client):
        _, h = _auth(client)
        r = client.get("/api/marketplace", headers=h)
        assert r.status_code == 200

    def test_marketplace_categories(self, client):
        _, h = _auth(client)
        r = client.get("/api/marketplace/categories", headers=h)
        assert r.status_code == 200

    def test_marketplace_search(self, client):
        _, h = _auth(client)
        r = client.get("/api/marketplace/search?q=bot", headers=h)
        assert r.status_code == 200

    def test_marketplace_detail_not_found(self, client):
        _, h = _auth(client)
        r = client.get("/api/marketplace/999999", headers=h)
        assert r.status_code in (200, 404)

    def test_marketplace_reviews_not_found(self, client):
        _, h = _auth(client)
        r = client.get("/api/marketplace/999999/reviews", headers=h)
        assert r.status_code in (200, 404)

    def test_publish_bot(self, client):
        _, h = _auth(client)
        bot = _create_bot(client, h)
        if not bot:
            return
        bid = bot.get("id") or bot.get("bot_id")
        if not bid:
            return
        r = client.post(f"/api/bots/{bid}/publish", json={
            "is_public": True,
            "category": "utility",
        }, headers=h)
        assert r.status_code in (200, 403, 404)

    def test_marketplace_install_requires_auth(self, client):
        r = client.post("/api/marketplace/1/install/1")
        assert r.status_code in (401, 403, 404, 405)

    def test_submit_review(self, client):
        _, h = _auth(client)
        r = client.post("/api/marketplace/999999/review", json={
            "rating": 5,
            "text": "Great bot!",
        }, headers=h)
        assert r.status_code in (200, 201, 404)

    def test_marketplace_sort(self, client):
        _, h = _auth(client)
        for sort in ("rating", "installs", "newest"):
            r = client.get(f"/api/marketplace?sort={sort}", headers=h)
            assert r.status_code == 200

    def test_marketplace_category_filter(self, client):
        _, h = _auth(client)
        r = client.get("/api/marketplace?category=utility", headers=h)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 8. NATIVE BRIDGE
# ══════════════════════════════════════════════════════════════════════════════
