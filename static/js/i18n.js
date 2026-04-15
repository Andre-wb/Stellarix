/**
 * Vortex i18n — lightweight internationalization module.
 *
 * Usage:
 *   import { t, setLocale, getLocale } from './i18n.js';
 *   t('chat.send')           → "Отправить" (ru) / "Send" (en)
 *   t('rooms.count', {n: 5}) → "5 участников"
 *
 * Features:
 *   - Auto-detect browser language
 *   - Fallback: requested key → Russian → key itself
 *   - Nested keys with dot notation
 *   - Simple interpolation: {key} → value
 *   - Language persisted in localStorage
 *   - Dynamic locale loading
 */

const STORAGE_KEY = 'vortex_locale';
const SUPPORTED = ['ru', 'en', 'uk', 'it', 'zh', 'es', 'de', 'th', 'fr', 'pt', 'ro', 'ca', 'nl', 'da', 'no', 'sv', 'is', 'be', 'pl', 'cs', 'sk', 'hr', 'sr', 'sl', 'bg', 'mk', 'el', 'hu', 'fi', 'et', 'lv', 'lt', 'tr', 'zh-TW', 'ja', 'ko', 'ar', 'he', 'fa', 'ur', 'sw', 'am', 'zu', 'af', 'tl', 'kk', 'ky', 'hy', 'ka', 'az', 'uz', 'hi', 'bn', 'mr', 'te', 'ta', 'kn', 'gu', 'pa', 'as', 'ne', 'si', 'id', 'ms', 'vi', 'km', 'my', 'lo', 'mn', 'ce', 'os', 'av', 'ba', 'tt', 'cv', 'udm', 'mhr', 'kv', 'sah', 'bua', 'tyv', 'ckt', 'crh', 'ab', 'ug', 'bo', 'ku', 'bal', 'ha', 'yo', 'ig', 'om', 'so', 'ga', 'mt', 'eu', 'gl', 'cy', 'lb', 'ht', 'qu', 'gn', 'jv', 'su', 'ceb', 'rw', 'mg', 'sn', 'tn', 'ps', 'sd', 'oc', 'eo', 'ml', 'or', 'mai', 'ff', 'ts', 'xh', 'bm', 'wo', 'ln', 'lg', 'mi', 'haw', 'la', 'sa', 'tok'];
const DEFAULT_LOCALE = 'ru';

let _currentLocale = DEFAULT_LOCALE;
let _translations = {};
let _fallback = {};

// ── Core translation function ───────────────────────────────────────────────

/**
 * Translate a key.
 * @param {string} key — dot-notation key, e.g. 'chat.send'
 * @param {Object} [params] — interpolation values, e.g. {n: 5}
 * @returns {string}
 */
export function t(key, params) {
    let str = _resolve(_translations, key) || _resolve(_fallback, key) || key;
    if (params) {
        for (const [k, v] of Object.entries(params)) {
            str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
        }
    }
    return str;
}

function _resolve(obj, key) {
    return key.split('.').reduce((o, k) => o?.[k], obj);
}

// ── Locale management ───────────────────────────────────────────────────────

export function getLocale() { return _currentLocale; }
export function getSupportedLocales() { return [...SUPPORTED]; }

/**
 * Set locale and load translations.
 * @param {string} locale — 'ru', 'en', etc.
 */
export async function setLocale(locale) {
    if (!SUPPORTED.includes(locale)) locale = DEFAULT_LOCALE;
    _currentLocale = locale;
    localStorage.setItem(STORAGE_KEY, locale);

    try {
        const resp = await fetch(`/static/locales/${locale}.json`);
        if (resp.ok) _translations = await resp.json();
    } catch (e) {
        console.warn('[i18n] Failed to load locale:', locale, e);
    }

    // Always load fallback (Russian)
    if (locale !== DEFAULT_LOCALE && !Object.keys(_fallback).length) {
        try {
            const resp = await fetch(`/static/locales/${DEFAULT_LOCALE}.json`);
            if (resp.ok) _fallback = await resp.json();
        } catch {}
    }

    // Update DOM elements with data-i18n attribute
    _updateDOM();

    document.documentElement.lang = locale;

    // RTL support for Arabic, Persian, Urdu
    const RTL_LOCALES = ['ar', 'he', 'fa', 'ur', 'ug', 'bal', 'ps', 'sd'];
    document.documentElement.dir = RTL_LOCALES.includes(locale) ? 'rtl' : 'ltr';

    // Rebuild Gravitix docs overlay with new language
    if (typeof window.gxDocsRebuild === 'function') window.gxDocsRebuild();
}

/**
 * Initialize i18n: detect language, load translations.
 */
export async function initI18n() {
    // Priority: localStorage → browser language → default
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) {
        await setLocale(saved);
        return;
    }

    const browserLang = (navigator.language || navigator.userLanguage || '').slice(0, 2).toLowerCase();
    const detected = SUPPORTED.includes(browserLang) ? browserLang : DEFAULT_LOCALE;
    await setLocale(detected);
}

// ── DOM auto-translation ────────────────────────────────────────────────────

/**
 * Update all elements with data-i18n attribute.
 * <span data-i18n="chat.send">Отправить</span>
 * <input data-i18n-placeholder="chat.placeholder">
 * <button data-i18n-title="chat.sendTitle">
 * <div data-i18n-aria="chat.ariaLabel">
 */
function _updateDOM() {
    // Text content
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const val = t(key);
        if (val !== key) el.textContent = val;
    });

    // Placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        const val = t(key);
        if (val !== key) el.placeholder = val;
    });

    // Title attributes
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        const val = t(key);
        if (val !== key) el.title = val;
    });

    // aria-label
    document.querySelectorAll('[data-i18n-aria]').forEach(el => {
        const key = el.getAttribute('data-i18n-aria');
        const val = t(key);
        if (val !== key) el.setAttribute('aria-label', val);
    });
}

// ── Utility ─────────────────────────────────────────────────────────────────

/**
 * Get current translations object (for modules that need bulk access).
 */
export function getTranslations() { return _translations; }
