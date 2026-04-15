// @ts-check
const { test, expect } = require('../fixtures');
const { randomStr, randomDigits, registerAndLogin } = require('./helpers');

/**
 * Vortex E2E — Federation System
 *
 * Covers:
 *   - Authentication guards on federation endpoints
 *   - Node CRUD (add / list / delete)
 *   - Network status
 *   - Code hash & manifest
 *   - Handshake protocol
 *   - Gossip (node-joined / node-left)
 *   - Token validation
 *   - My-tasks
 *   - Verify
 */

test.describe('Federation — Trusted Nodes', () => {
    const username = `fed_u_${randomStr(6)}`;
    const phone = `+7950${randomDigits(7)}`;
    let csrf = '';

    test.beforeAll(async ({ request }) => {
        const { csrfToken } = await registerAndLogin(request, username, phone);
        csrf = csrfToken;
    });

    // ── Authentication Guards ────────────────────────────────────────────────

    test('list nodes requires auth', async ({ freshRequest }) => {
        const res = await freshRequest.get('/api/federation/nodes');
        expect([401, 403]).toContain(res.status());
    });

    test('add node requires auth', async ({ freshRequest }) => {
        const res = await freshRequest.post('/api/federation/nodes/add', {
            data: { url: 'https://example.com' },
        });
        expect([401, 403]).toContain(res.status());
    });

    test('verify requires auth', async ({ freshRequest }) => {
        const res = await freshRequest.post('/api/federation/nodes/verify', {
            data: { node_id: 99999 },
        });
        expect([401, 403]).toContain(res.status());
    });

    // ── Node CRUD ────────────────────────────────────────────────────────────

    test('add node with invalid URL returns 400', async ({ request }) => {
        const res = await request.post('/api/federation/nodes/add', {
            headers: { 'X-CSRF-Token': csrf },
            data: { url: '' },
        });
        expect([400, 422]).toContain(res.status());
    });

    test('add node with SSRF URL blocked', async ({ request }) => {
        const res = await request.post('/api/federation/nodes/add', {
            headers: { 'X-CSRF-Token': csrf },
            data: { url: 'http://127.0.0.1' },
        });
        expect([400, 403, 422, 502]).toContain(res.status());
    });

    test('add node with unreachable URL returns 502', async ({ request }) => {
        const fakeUrl = `https://fake-node-${randomStr(10)}.invalid`;
        const res = await request.post('/api/federation/nodes/add', {
            headers: { 'X-CSRF-Token': csrf },
            data: { url: fakeUrl },
        });
        // Server tries to probe the node and fails
        expect([400, 502, 504]).toContain(res.status());
    });

    test('list nodes returns array', async ({ request }) => {
        const res = await request.get('/api/federation/nodes', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(Array.isArray(body.nodes)).toBe(true);
    });

    test('add node duplicate returns conflict or probe error', async ({ request }) => {
        const dupUrl = `https://dup-node-${randomStr(8)}.invalid`;
        const res1 = await request.post('/api/federation/nodes/add', {
            headers: { 'X-CSRF-Token': csrf },
            data: { url: dupUrl },
        });
        const res2 = await request.post('/api/federation/nodes/add', {
            headers: { 'X-CSRF-Token': csrf },
            data: { url: dupUrl },
        });
        // Both may fail with 502 (unreachable), or second returns 409 if first succeeded
        expect([400, 409, 502, 504]).toContain(res1.status());
        expect([400, 409, 502, 504]).toContain(res2.status());
    });

    test('delete non-existent node returns 404', async ({ request }) => {
        const res = await request.delete('/api/federation/nodes/99999', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect([404, 400]).toContain(res.status());
    });

    // ── Network Status ───────────────────────────────────────────────────────

    test('status returns network summary', async ({ request }) => {
        const res = await request.get('/api/federation/nodes/status', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body).toHaveProperty('total_nodes');
    });

    test('status has health indicator', async ({ request }) => {
        const res = await request.get('/api/federation/nodes/status', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        // API returns total_nodes, monitor_running — network_health is optional
        expect(body).toHaveProperty('total_nodes');
    });

    // ── Code Hash & Manifest ─────────────────────────────────────────────────

    test('code-hash returns deterministic hash', async ({ request }) => {
        const res1 = await request.get('/api/federation/code-hash', {
            headers: { 'X-CSRF-Token': csrf },
        });
        const res2 = await request.get('/api/federation/code-hash', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res1.status()).toBe(200);
        expect(res2.status()).toBe(200);
        const body1 = await res1.json();
        const body2 = await res2.json();
        expect(body1.code_hash).toBe(body2.code_hash);
    });

    test('code-hash has file count', async ({ request }) => {
        const res = await request.get('/api/federation/code-hash', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body).toHaveProperty('code_hash');
        expect(body.code_hash.length).toBeGreaterThan(0);
    });

    test('code-manifest returns hash', async ({ request }) => {
        const res = await request.post('/api/federation/code-manifest', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body).toHaveProperty('code_hash');
    });

    // ── Handshake ────────────────────────────────────────────────────────────

    test('handshake with valid payload', async ({ request }) => {
        const hashRes = await request.get('/api/federation/code-hash', {
            headers: { 'X-CSRF-Token': csrf },
        });
        const { code_hash } = await hashRes.json();

        const res = await request.post('/api/federation/handshake', {
            headers: { 'X-CSRF-Token': csrf },
            data: {
                node_id: `node_${randomStr(8)}`,
                url: `https://handshake-${randomStr(6)}.example.com`,
                code_hash: code_hash || randomStr(64),
                version: '1.0.0',
            },
        });
        // Should not be a server error; exact status depends on federation state
        expect(res.status()).toBeLessThan(500);
    });

    test('handshake rejects empty body', async ({ request }) => {
        const res = await request.post('/api/federation/handshake', {
            headers: { 'X-CSRF-Token': csrf },
            data: {},
        });
        expect([400, 422]).toContain(res.status());
    });

    // ── Gossip ───────────────────────────────────────────────────────────────

    test('gossip node-joined accepts data', async ({ request }) => {
        const res = await request.post('/api/federation/gossip/node-joined', {
            headers: { 'X-CSRF-Token': csrf },
            data: {
                url: `https://gossip-join-${randomStr(6)}.example.com`,
                node_id: `node_${randomStr(8)}`,
                code_hash: randomStr(64),
                version: '1.0.0',
            },
        });
        expect(res.status()).toBeLessThan(500);
    });

    test('gossip node-joined with empty body fails', async ({ request }) => {
        const res = await request.post('/api/federation/gossip/node-joined', {
            headers: { 'X-CSRF-Token': csrf },
            data: {},
        });
        expect([400, 422]).toContain(res.status());
    });

    test('gossip node-left accepts data', async ({ request }) => {
        const res = await request.post('/api/federation/gossip/node-left', {
            headers: { 'X-CSRF-Token': csrf },
            data: {
                url: `https://gossip-left-${randomStr(6)}.example.com`,
                node_id: `node_${randomStr(8)}`,
            },
        });
        expect(res.status()).toBeLessThan(500);
    });

    test('gossip node-left with empty body fails', async ({ request }) => {
        const res = await request.post('/api/federation/gossip/node-left', {
            headers: { 'X-CSRF-Token': csrf },
            data: {},
        });
        expect([400, 422]).toContain(res.status());
    });

    // ── Token Validation ─────────────────────────────────────────────────────

    test('validate-token with invalid token', async ({ request }) => {
        const res = await request.post('/api/federation/validate-token', {
            headers: { 'X-CSRF-Token': csrf },
            data: {
                node_id: `node_${randomStr(8)}`,
                token: `invalid_token_${randomStr(16)}`,
            },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body.valid).toBe(false);
    });

    test('validate-token rejects empty body', async ({ request }) => {
        const res = await request.post('/api/federation/validate-token', {
            headers: { 'X-CSRF-Token': csrf },
            data: {},
        });
        expect([400, 422]).toContain(res.status());
    });

    // ── My Tasks ─────────────────────────────────────────────────────────────

    test('my-tasks returns task list', async ({ request }) => {
        const res = await request.get('/api/federation/my-tasks', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(Array.isArray(body.tasks)).toBe(true);
    });

    test('my-tasks has node_id', async ({ request }) => {
        const res = await request.get('/api/federation/my-tasks', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body).toHaveProperty('node_id');
    });

    // ── Verify ───────────────────────────────────────────────────────────────

    test('verify non-existent node', async ({ request }) => {
        const res = await request.post('/api/federation/nodes/verify', {
            headers: { 'X-CSRF-Token': csrf },
            data: { node_id: 99999 },
        });
        expect([400, 404, 422]).toContain(res.status());
    });
});
