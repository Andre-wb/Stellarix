"""Тесты для системы доверенных узлов федерации (trusted nodes)."""

import secrets

import pytest

from conftest import SyncASGIClient, make_user, login_user, random_str


def _csrf_headers(client: SyncASGIClient) -> dict:
    """Get a fresh CSRF token header for unauthenticated POST requests."""
    r = client.get('/api/authentication/csrf-token')
    token = r.json().get('csrf_token', '')
    return {'X-CSRF-Token': token}


class TestFederationNodes:
    """Tests for federation trusted nodes management."""

    # ── Node CRUD ────────────────────────────────────────────────────────────

    def test_add_node_invalid_url(self, client: SyncASGIClient, logged_user: dict):
        """Empty URL / no scheme → 400/422."""
        r = client.post('/api/federation/nodes/add', json={
            'url': '',
        }, headers=logged_user['headers'])
        assert r.status_code in (400, 422)

        r2 = client.post('/api/federation/nodes/add', json={
            'url': 'no-scheme-host.example.com',
        }, headers=logged_user['headers'])
        assert r2.status_code in (400, 422)

    def test_add_node_ssrf_blocked(self, client: SyncASGIClient, logged_user: dict):
        """Blocked IP addresses must be rejected (SSRF protection) → 400."""
        # 169.254.x.x (link-local) is in the blocked list; localhost is allowed
        r = client.post('/api/federation/nodes/add', json={
            'url': 'https://169.254.169.254',
        }, headers=logged_user['headers'])
        assert r.status_code == 400

    def test_add_node_unreachable(self, client: SyncASGIClient, logged_user: dict):
        """Unreachable host → 502 (probe fails)."""
        r = client.post('/api/federation/nodes/add', json={
            'url': 'https://nonexistent.invalid:9999',
        }, headers=logged_user['headers'])
        assert r.status_code == 502

    def test_list_nodes_empty(self, client: SyncASGIClient, logged_user: dict):
        """GET nodes when none added → 200, empty or existing list."""
        r = client.get('/api/federation/nodes', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'nodes' in body
        assert isinstance(body['nodes'], list)

    def test_list_nodes_unauthenticated(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """GET without auth → 401/403."""
        r = anon_client.get('/api/federation/nodes')
        assert r.status_code in (401, 403)

    def test_add_node_duplicate(self, client: SyncASGIClient, logged_user: dict):
        """Adding the same URL twice — second attempt should be 409.

        Register a node via handshake first (no probe needed), then try /nodes/add.
        """
        tag = random_str()
        url = f'https://dup-test-{tag}.example.com:8443'

        # Create node via handshake (doesn't probe, just registers)
        local_hash = client.get('/api/federation/code-hash').json()['code_hash']
        client.post('/api/federation/handshake', json={
            'node_id': secrets.token_hex(16),
            'url': url,
            'code_hash': local_hash,
            'version': '1.0.0',
        }, headers=logged_user['headers'])

        # Now try to add the same URL via /nodes/add — should be 409 (duplicate)
        r = client.post('/api/federation/nodes/add', json={
            'url': url,
        }, headers=logged_user['headers'])
        assert r.status_code == 409

    def test_delete_node_not_found(self, client: SyncASGIClient, logged_user: dict):
        """DELETE non-existent node → 404."""
        r = client.delete('/api/federation/nodes/999999', headers=logged_user['headers'])
        assert r.status_code == 404

    def test_delete_node_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """DELETE without auth → 401/403."""
        r = anon_client.delete('/api/federation/nodes/1')
        assert r.status_code in (401, 403)

    # ── Network Status ────────────────────────────────────────────────────────

    def test_network_status_empty(self, client: SyncASGIClient, logged_user: dict):
        """GET status → 200, contains expected fields."""
        r = client.get('/api/federation/nodes/status', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'total_nodes' in body
        assert 'local_node_id' in body
        assert 'local_code_hash' in body
        assert isinstance(body['total_nodes'], int)

    def test_network_status_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """GET status without auth → 401/403."""
        r = anon_client.get('/api/federation/nodes/status')
        assert r.status_code in (401, 403)

    # ── Code Verification ─────────────────────────────────────────────────────

    def test_code_hash_returns_hash(self, client: SyncASGIClient):
        """GET code-hash → 200, has code_hash string field."""
        r = client.get('/api/federation/code-hash')
        assert r.status_code == 200
        body = r.json()
        assert 'code_hash' in body
        assert isinstance(body['code_hash'], str)
        assert len(body['code_hash']) == 64  # sha256 hex

    def test_code_manifest_returns_hash(self, client: SyncASGIClient, logged_user: dict):
        """POST code-manifest → 200, has code_hash and file_count."""
        r = client.post('/api/federation/code-manifest', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'code_hash' in body
        assert 'file_count' in body
        assert isinstance(body['code_hash'], str)
        assert isinstance(body['file_count'], int)
        assert body['file_count'] > 0

    def test_code_hash_deterministic(self, client: SyncASGIClient):
        """Calling code-hash twice gives the same result."""
        r1 = client.get('/api/federation/code-hash')
        r2 = client.get('/api/federation/code-hash')
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()['code_hash'] == r2.json()['code_hash']

    # ── Handshake ─────────────────────────────────────────────────────────────

    def test_handshake_missing_fields(self, client: SyncASGIClient, logged_user: dict):
        """POST handshake with empty body → 422."""
        r = client.post('/api/federation/handshake', json={}, headers=logged_user['headers'])
        assert r.status_code == 422

    def test_handshake_with_valid_data(self, client: SyncASGIClient, logged_user: dict):
        """POST handshake with valid-looking data → 200 (accepted or rejected based on hash)."""
        tag = random_str()
        local_hash = client.get('/api/federation/code-hash').json()['code_hash']

        r = client.post('/api/federation/handshake', json={
            'node_id': secrets.token_hex(16),
            'url': f'https://handshake-test-{tag}.example.com:8443',
            'code_hash': local_hash,
            'version': '1.0.0',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'accepted' in body
        assert 'code_hash' in body

    def test_handshake_wrong_hash_rejected(self, client: SyncASGIClient, logged_user: dict):
        """POST handshake with wrong code_hash → 200 but accepted=false."""
        tag = random_str()
        r = client.post('/api/federation/handshake', json={
            'node_id': secrets.token_hex(16),
            'url': f'https://badhash-{tag}.example.com:8443',
            'code_hash': 'a' * 64,  # wrong hash
            'version': '1.0.0',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert body['accepted'] is False
        assert body.get('reason') == 'code_hash_mismatch'

    # ── Gossip ────────────────────────────────────────────────────────────────

    def test_gossip_node_joined(self, client: SyncASGIClient, logged_user: dict):
        """POST gossip/node-joined with valid data → 200."""
        tag = random_str()
        local_hash = client.get('/api/federation/code-hash').json()['code_hash']

        r = client.post('/api/federation/gossip/node-joined', json={
            'node_id': secrets.token_hex(16),
            'url': f'https://gossip-join-{tag}.example.com:8443',
            'code_hash': local_hash,
            'version': '1.0.0',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'status' in body

    def test_gossip_node_left(self, client: SyncASGIClient, logged_user: dict):
        """POST gossip/node-left with valid data → 200."""
        r = client.post('/api/federation/gossip/node-left', json={
            'node_id': secrets.token_hex(16),
            'url': 'https://gossip-left.example.com:8443',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'status' in body

    # ── Token Validation ──────────────────────────────────────────────────────

    def test_validate_token_invalid(self, client: SyncASGIClient, logged_user: dict):
        """POST with wrong token → 200 with valid=false."""
        r = client.post('/api/federation/validate-token', json={
            'node_id': 'nonexistent-node-id',
            'token': 'definitely-not-a-real-token',
        }, headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert body['valid'] is False

    def test_validate_token_missing_fields(self, client: SyncASGIClient, logged_user: dict):
        """POST empty body → 422."""
        r = client.post('/api/federation/validate-token', json={}, headers=logged_user['headers'])
        assert r.status_code == 422

    # ── My Tasks ──────────────────────────────────────────────────────────────

    def test_my_tasks_returns_list(self, client: SyncASGIClient, logged_user: dict):
        """GET my-tasks → 200, has tasks array."""
        r = client.get('/api/federation/my-tasks', headers=logged_user['headers'])
        assert r.status_code == 200
        body = r.json()
        assert 'node_id' in body
        assert 'tasks' in body
        assert isinstance(body['tasks'], list)

    def test_my_tasks_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        """GET my-tasks without auth → 401/403."""
        r = anon_client.get('/api/federation/my-tasks')
        assert r.status_code in (401, 403)
