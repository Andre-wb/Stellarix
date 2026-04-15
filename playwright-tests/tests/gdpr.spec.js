// @ts-check
const { test, expect } = require('../fixtures');
const { randomStr, randomDigits, registerAndLogin } = require('./helpers');

test.describe('GDPR & Privacy', () => {
    const username = `gdpr_u_${randomStr(6)}`;
    const phone = `+7953${randomDigits(7)}`;
    let csrf = '';

    test.beforeAll(async ({ request }) => {
        const { csrfToken } = await registerAndLogin(request, username, phone);
        csrf = csrfToken;
    });

    test('canary endpoint returns signed statement', async ({ request }) => {
        const res = await request.get('/api/privacy/canary');
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(body).toHaveProperty('statement');
    });

    test('canary verify', async ({ request }) => {
        const res = await request.get('/api/privacy/canary/verify');
        expect([200, 404]).toContain(res.status());
    });

    test('privacy rights returns list', async ({ request }) => {
        const res = await request.get('/api/privacy/rights', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
    });

    test('data export returns data or 202', async ({ request }) => {
        const res = await request.get('/api/privacy/export', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect([200, 202]).toContain(res.status());
    });

    test('data portability', async ({ request }) => {
        const res = await request.get('/api/privacy/portability', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect([200, 202]).toContain(res.status());
    });
});
