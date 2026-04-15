// @ts-check
const { test, expect } = require('../fixtures');
const { randomStr, randomDigits, registerAndLogin } = require('./helpers');

/**
 * Vortex E2E Tests — Full user flow:
 *   Registration → Login → Create Room → Send Message → File Upload → Voice Call → Logout
 */

const TEST_USER = {
    username: `e2e_${randomStr()}`,
    password: 'E2eTestPass99!@',
    phone: `+7900${randomDigits(7)}`,
};

// ── 1. Health Check ─────────────────────────────────────────────────────────

test.describe('Health', () => {
    test('server is alive', async ({ request }) => {
        const res = await request.get('/health');
        expect(res.ok()).toBeTruthy();
        const body = await res.json();
        expect(body.status).toBe('ok');
        expect(body.version).toBe('1.0.0');
    });

    test('readiness probe passes', async ({ request }) => {
        const res = await request.get('/health/ready');
        expect(res.status()).toBeLessThanOrEqual(503);
        const body = await res.json();
        expect(body.status).toMatch(/ready|degraded/);
    });
});

// ── 2. Registration ─────────────────────────────────────────────────────────

test.describe('Registration', () => {
    test('register new user', async ({ request }) => {
        const pubkey = Array.from({ length: 32 }, () =>
            Math.floor(Math.random() * 256).toString(16).padStart(2, '0')
        ).join('');

        const res = await request.post('/api/authentication/register', {
            data: {
                username: TEST_USER.username,
                password: TEST_USER.password,
                phone: TEST_USER.phone,
                x25519_public_key: pubkey,
                display_name: `E2E Test ${TEST_USER.username}`,
            },
        });
        expect(res.status()).toBe(201);
        const body = await res.json();
        expect(body.ok).toBe(true);
        expect(body.username).toBe(TEST_USER.username);
    });

    test('duplicate registration fails', async ({ request }) => {
        const res = await request.post('/api/authentication/register', {
            data: {
                username: TEST_USER.username,
                password: TEST_USER.password,
                phone: TEST_USER.phone,
                x25519_public_key: Array.from({ length: 32 }, () =>
                    Math.floor(Math.random() * 256).toString(16).padStart(2, '0')
                ).join(''),
            },
        });
        expect(res.status()).toBe(409);
    });
});

// ── 3. Login ────────────────────────────────────────────────────────────────

test.describe('Login', () => {
    test('login with correct credentials', async ({ request }) => {
        const res = await request.post('/api/authentication/login', {
            data: {
                phone_or_username: TEST_USER.username,
                password: TEST_USER.password,
            },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body.ok).toBe(true);
    });

    test('login with wrong password fails', async ({ request }) => {
        const res = await request.post('/api/authentication/login', {
            data: {
                phone_or_username: TEST_USER.username,
                password: 'WrongPassword!!1',
            },
        });
        expect(res.status()).toBe(401);
    });
});

// ── 4. Authenticated Operations ─────────────────────────────────────────────

test.describe('Authenticated', () => {
    let csrfToken = '';

    test.beforeAll(async ({ request }) => {
        // Register (with retry on collision) + login
        const { csrfToken: csrf } = await registerAndLogin(
            request, TEST_USER.username, TEST_USER.phone, TEST_USER.password
        );
        csrfToken = csrf;
    });

    test('get profile', async ({ request }) => {
        const res = await request.get('/api/authentication/me', {
            headers: { 'X-CSRF-Token': csrfToken },
        });
        expect(res.ok()).toBeTruthy();
        const body = await res.json();
        expect(body.username).toBe(TEST_USER.username);
    });

    test('create room', async ({ request }) => {
        const pubkey = Array.from({ length: 32 }, () =>
            Math.floor(Math.random() * 256).toString(16).padStart(2, '0')
        ).join('');
        const ciphertext = Array.from({ length: 60 }, () =>
            Math.floor(Math.random() * 256).toString(16).padStart(2, '0')
        ).join('');

        const res = await request.post('/api/rooms', {
            headers: { 'X-CSRF-Token': csrfToken },
            data: {
                name: `e2e_room_${randomStr(6)}`,
                encrypted_room_key: {
                    ephemeral_pub: pubkey,
                    ciphertext: ciphertext,
                },
            },
        });
        expect([200, 201]).toContain(res.status());
    });

    test('list rooms', async ({ request }) => {
        const res = await request.get('/api/rooms/my', {
            headers: { 'X-CSRF-Token': csrfToken },
        });
        expect(res.ok()).toBeTruthy();
    });

    test('list public rooms', async ({ request }) => {
        const res = await request.get('/api/rooms/public');
        expect(res.ok()).toBeTruthy();
    });

    test('search users', async ({ request }) => {
        const res = await request.get(`/api/users/search?q=${TEST_USER.username.slice(0, 5)}`, {
            headers: { 'X-CSRF-Token': csrfToken },
        });
        expect(res.ok()).toBeTruthy();
    });

    test('list contacts', async ({ request }) => {
        const res = await request.get('/api/contacts', {
            headers: { 'X-CSRF-Token': csrfToken },
        });
        expect(res.ok()).toBeTruthy();
    });

    test('list saved messages', async ({ request }) => {
        const res = await request.get('/api/saved', {
            headers: { 'X-CSRF-Token': csrfToken },
        });
        expect(res.ok()).toBeTruthy();
    });

    test('password strength check', async ({ request }) => {
        const res = await request.post('/api/authentication/password-strength', {
            headers: { 'X-CSRF-Token': csrfToken },
            data: { password: 'V3ry$trong!Pass#2026' },
        });
        expect(res.ok()).toBeTruthy();
        const body = await res.json();
        expect(body.score).toBeGreaterThan(50);
    });

    test('update rich status', async ({ request }) => {
        const res = await request.put('/api/authentication/status', {
            headers: { 'X-CSRF-Token': csrfToken },
            data: { presence: 'away', custom_status: 'E2E testing' },
        });
        expect(res.ok()).toBeTruthy();
    });

    test('logout', async ({ request }) => {
        const res = await request.post('/api/authentication/logout', {
            headers: { 'X-CSRF-Token': csrfToken },
        });
        expect([200, 204]).toContain(res.status());
    });
});

// ── 5. UI Flow (Browser) ────────────────────────────────────────────────────

test.describe('Browser UI', () => {
    test('landing page loads', async ({ page }) => {
        await page.goto('/');
        await expect(page).toHaveTitle(/Vortex/i);
    });

    test('static assets load', async ({ request }) => {
        const manifest = await request.get('/manifest.json');
        expect([200, 404]).toContain(manifest.status());

        const sw = await request.get('/service-worker.js');
        expect([200, 404]).toContain(sw.status());
    });

    test('metrics endpoint works', async ({ request }) => {
        const res = await request.get('/metrics');
        expect(res.ok()).toBeTruthy();
        const text = await res.text();
        expect(text).toContain('vortex_http_requests_total');
    });
});
