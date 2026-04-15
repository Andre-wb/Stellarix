// @ts-check
const { test, expect } = require('../fixtures');
const { randomStr, randomDigits, registerAndLogin } = require('./helpers');

test.describe('AI Assistant', () => {
    const username = `ai_u_${randomStr(6)}`;
    const phone = `+7955${randomDigits(7)}`;
    let csrf = '';

    test.beforeAll(async ({ request }) => {
        const { csrfToken } = await registerAndLogin(request, username, phone);
        csrf = csrfToken;
    });

    test('AI status endpoint', async ({ request }) => {
        const res = await request.get('/api/ai/status', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect([200, 503]).toContain(res.status());
    });

    test('AI chat returns response or service unavailable', async ({ request }) => {
        const res = await request.post('/api/ai/chat', {
            headers: { 'X-CSRF-Token': csrf },
            data: { message: 'Hello AI' },
        });
        expect([200, 400, 503]).toContain(res.status());
    });

    test('AI fix-text', async ({ request }) => {
        const res = await request.post('/api/ai/fix-text', {
            headers: { 'X-CSRF-Token': csrf },
            data: { text: 'helo wrld' },
        });
        expect([200, 400, 503]).toContain(res.status());
    });

    test('AI suggest', async ({ request }) => {
        const res = await request.post('/api/ai/suggest', {
            headers: { 'X-CSRF-Token': csrf },
            data: { context: 'How are you?' },
        });
        expect([200, 400, 503]).toContain(res.status());
    });
});
