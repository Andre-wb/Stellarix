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


class TestSecurityQuestions:
    def test_get_defaults(self, client):
        r = client.get("/api/authentication/security-questions/defaults")
        assert r.status_code == 200
        data = r.json()
        # May return {en: [...]} or {questions: [...]} or a list
        assert isinstance(data, (dict, list))

    def test_setup_security_questions(self, client):
        _, h = _auth(client)
        r = client.post("/api/authentication/security-questions/setup", json={
            "questions": ["What is your pet?", "Your city?", "Favorite color?"],
            "answers": ["Rex", "Moscow", "Blue"],
        }, headers=h)
        assert r.status_code in (200, 201)

    def test_setup_incomplete_rejected(self, client):
        _, h = _auth(client)
        r = client.post("/api/authentication/security-questions/setup", json={
            "questions": ["Only one?"],
            "answers": ["Yes"],
        }, headers=h)
        assert r.status_code in (400, 422)

    def test_load_questions(self, client):
        u, h = _auth(client)
        # Setup first
        client.post("/api/authentication/security-questions/setup", json={
            "questions": ["Q1?", "Q2?", "Q3?"],
            "answers": ["A1", "A2", "A3"],
        }, headers=h)
        # Load
        username = u.get("username", "")
        r = client.post("/api/authentication/security-questions/load", json={
            "username": username,
        }, headers=h)
        assert r.status_code in (200, 404)

    def test_recover_wrong_answers(self, client):
        u, h = _auth(client)
        client.post("/api/authentication/security-questions/setup", json={
            "questions": ["Q1?", "Q2?", "Q3?"],
            "answers": ["A1", "A2", "A3"],
        }, headers=h)
        r = client.post("/api/authentication/security-questions/recover", json={
            "username": u.get("username", ""),
            "answers": ["WRONG", "WRONG", "WRONG"],
        })
        assert r.status_code in (400, 401, 403)

    def test_recover_requires_setup(self, client):
        u, _ = _auth(client)
        r = client.post("/api/authentication/security-questions/recover", json={
            "username": u.get("username", ""),
            "answers": ["a", "b", "c"],
        })
        assert r.status_code in (400, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 4. CONTACT SYNC
# ══════════════════════════════════════════════════════════════════════════════
