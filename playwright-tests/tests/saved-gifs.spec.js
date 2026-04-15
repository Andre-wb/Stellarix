// @ts-check
const { test, expect } = require('../fixtures');
const { randomStr, randomDigits, registerAndLogin } = require('./helpers');

test.describe('Saved GIFs', () => {
    const username = `gif_u_${randomStr(6)}`;
    const phone = `+7954${randomDigits(7)}`;
    let csrf = '';

    test.beforeAll(async ({ request }) => {
        const { csrfToken } = await registerAndLogin(request, username, phone);
        csrf = csrfToken;
    });

    test('list saved gifs (empty)', async ({ request }) => {
        const res = await request.get('/api/gifs/saved', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
    });

    test('save a gif', async ({ request }) => {
        const res = await request.post('/api/gifs/saved', {
            headers: { 'X-CSRF-Token': csrf },
            data: { url: 'https://example.com/test.gif' },
        });
        expect([200, 201]).toContain(res.status());
    });

    test('list saved gifs after save', async ({ request }) => {
        const res = await request.get('/api/gifs/saved', {
            headers: { 'X-CSRF-Token': csrf },
        });
        expect(res.status()).toBe(200);
        const body = await res.json();
        expect(Array.isArray(body.gifs || body)).toBe(true);
    });
});
