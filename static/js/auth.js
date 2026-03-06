// static/js/auth.js
import { $, api, showAlert, openModal, closeModal } from './utils.js';

// ============================================================================
// X25519 КЛЮЧЕВАЯ ПАРА
// ============================================================================

/**
 * Генерирует X25519 ключевую пару.
 * ВАЖНО: Web Crypto API не позволяет экспортировать X25519 private key как 'raw'
 * — только 'jwk'. Поэтому храним приватный ключ как JWK JSON-строку.
 */
async function generateX25519Keypair() {
    try {
        const keyPair = await crypto.subtle.generateKey(
            { name: 'X25519' }, true, ['deriveBits']
        );
        const publicRaw  = await crypto.subtle.exportKey('raw', keyPair.publicKey);
        const privateJwk = await crypto.subtle.exportKey('jwk', keyPair.privateKey);
        const toHex = b => Array.from(new Uint8Array(b)).map(x => x.toString(16).padStart(2,'0')).join('');
        return {
            publicKeyHex:  toHex(publicRaw),
            privateKeyJwk: JSON.stringify(privateJwk),
        };
    } catch (e) {
        console.error('X25519 generateKey failed:', e);
        throw new Error('Браузер не поддерживает X25519. Обновите до Chrome 113+, Firefox 118+ или Safari 17+.');
    }
}

function savePrivateKey(jwkString) {
    localStorage.setItem('vortex_x25519_priv', jwkString);
}

export function loadPrivateKey() {
    return localStorage.getItem('vortex_x25519_priv');
}

// ============================================================================
// AUTH
// ============================================================================

export function switchTab(tab) {
    $('login-form').style.display    = tab === 'login' ? '' : 'none';
    $('register-form').style.display = tab === 'register' ? '' : 'none';
    document.querySelectorAll('.auth-tab').forEach((t, i) => {
        t.classList.toggle('active', (i === 0) === (tab === 'login'));
    });
    $('auth-alert').classList.remove('show');
}

export function selectEmoji(btn) {
    document.querySelectorAll('.emoji-btn').forEach(b => b.classList.remove('emoji-selected'));
    btn.classList.add('emoji-selected');
    window.AppState.selectedEmoji = btn.dataset.emoji;
}

export async function doLogin() {
    try {
        const data = await api('POST', '/api/authentication/login', {
            phone_or_username: $('l-login').value.trim(),
            password:          $('l-pass').value,
        });
        window.AppState.user = data;
        const saved = loadPrivateKey();
        if (saved) window.AppState.x25519PrivateKey = saved;
        else console.warn('⚠️ Приватный ключ не найден');
        window.bootApp();
    } catch (e) {
        showAlert('auth-alert', e.message);
    }
}

export async function doRegister() {
    // Блокируем кнопку чтобы не отправить дважды
    const btn = document.querySelector('#register-form .btn-primary');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Создание...'; }

    try {
        // Генерируем keypair ДО запроса к серверу
        const { publicKeyHex, privateKeyJwk } = await generateX25519Keypair();

        const data = await api('POST', '/api/authentication/register', {
            phone:             $('r-phone').value.trim(),
            username:          $('r-username').value.trim(),
            password:          $('r-pass').value,
            display_name:      $('r-display').value.trim(),
            avatar_emoji:      window.AppState.selectedEmoji,
            x25519_public_key: publicKeyHex,  // только публичный ключ на сервер
        });

        // Приватный ключ — только локально, сервер никогда не видит
        savePrivateKey(privateKeyJwk);
        window.AppState.x25519PrivateKey = privateKeyJwk;
        window.AppState.user = data;
        console.info('🔑 X25519 keypair создан, приватный ключ сохранён в localStorage');
        window.bootApp();
    } catch (e) {
        showAlert('auth-alert', e.message);
        if (btn) { btn.disabled = false; btn.textContent = 'Создать аккаунт'; }
    }
}

export async function doLogout() {
    try { await api('POST', '/api/authentication/logout'); } catch {}
    window.AppState.user             = null;
    window.AppState.x25519PrivateKey = null;
    window.AppState.ws?.close();
    window.AppState.ws = null;
    $('app').style.display         = 'none';
    $('auth-screen').style.display = 'flex';
    $('auth-screen').className     = 'screen active';
}

export async function checkSession() {
    try {
        const data = await api('GET', '/api/authentication/me');
        window.AppState.user = data;
        const saved = loadPrivateKey();
        if (saved) window.AppState.x25519PrivateKey = saved;
        window.bootApp();
    } catch {
        // не авторизован
    }
}