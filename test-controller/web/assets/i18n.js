/* ============================================================================
 * Controller website i18n — mirrors static/js/i18n.js from the main Vortex app
 *
 * - Auto-detect browser language
 * - Loads /locales/<code>.json from the same origin
 * - English is the ultimate fallback
 * - Safe DOM construction for strings containing whitelisted tags (<strong>, <br>)
 * ========================================================================== */

(() => {
    'use strict';

    const STORAGE_KEY = 'vortexx_controller_locale';
    const DEFAULT_LOCALE = 'en';

    const SUPPORTED = [
        'en','ru','uk','es','fr','de','it','pt','zh','zh-TW','ja','ko','ar','hi',
        'tr','pl','nl','th','vi','id','cs','sv','ro','hu','el','da','fi','no','he',
        'fa','bg','hr','sr','sk','sl','lt','lv','et','ka','hy','az','kk','uz','bn',
        'ms','af','sw','ca','eu','gl','is','mk','be','mn','ky','ur','ta','te','mr',
        'gu','kn','ml','pa','ne','si','km','my','tl','zu','eo','ga','cy','so','ku',
        'am','ha','sq','bs','tg','tk','ti','yi','ny','st','gd','fy','co','sm','ay',
        'ee','ak',
        // extended set (total 130 locales, matching main Vortex minus 16 Cloud-only)
        'as','bho','bm','ceb','ckb','doi','dv','gn','haw','hmn','ht','ig','ilo','jv',
        'kri','la','lb','lg','ln','lo','lus','mai','mg','mi','mt','nso','om','or',
        'ps','qu','rw','sa','sd','sn','su','tt','ug','xh','yo',
    ];

    const NAMES = {
        en:'English', ru:'Русский', uk:'Українська', es:'Español', fr:'Français',
        de:'Deutsch', it:'Italiano', pt:'Português', zh:'中文', 'zh-TW':'繁體中文',
        ja:'日本語', ko:'한국어', ar:'العربية', hi:'हिन्दी', tr:'Türkçe',
        pl:'Polski', nl:'Nederlands', th:'ไทย', vi:'Tiếng Việt', id:'Bahasa Indonesia',
        cs:'Čeština', sv:'Svenska', ro:'Română', hu:'Magyar', el:'Ελληνικά',
        da:'Dansk', fi:'Suomi', no:'Norsk', he:'עברית', fa:'فارسی',
        bg:'Български', hr:'Hrvatski', sr:'Српски', sk:'Slovenčina', sl:'Slovenščina',
        lt:'Lietuvių', lv:'Latviešu', et:'Eesti', ka:'ქართული', hy:'Հայերեն',
        az:'Azərbaycan', kk:'Қазақша', uz:'Oʻzbek', bn:'বাংলা', ms:'Bahasa Melayu',
        af:'Afrikaans', sw:'Kiswahili', ca:'Català', eu:'Euskara', gl:'Galego',
        is:'Íslenska', mk:'Македонски', be:'Беларуская', mn:'Монгол', ky:'Кыргызча',
        ur:'اردو', ta:'தமிழ்', te:'తెలుగు', mr:'मराठी', gu:'ગુજરાતી',
        kn:'ಕನ್ನಡ', ml:'മലയാളം', pa:'ਪੰਜਾਬੀ', ne:'नेपाली', si:'සිංහල',
        km:'ភាសាខ្មែរ', my:'မြන်မာ', tl:'Filipino', zu:'isiZulu', eo:'Esperanto',
        ga:'Gaeilge', cy:'Cymraeg', so:'Soomaali', ku:'Kurdî', am:'አማርኛ',
        ha:'Hausa', sq:'Shqip', bs:'Bosanski', tg:'Тоҷикӣ', tk:'Türkmen',
        ti:'ትግርኛ', yi:'ייִדיש', ny:'Chichewa', st:'Sesotho', gd:'Gàidhlig',
        fy:'Frysk', co:'Corsu', sm:'Gagana Sāmoa', ay:'Aymar aru', ee:'Eʋegbe',
        ak:'Akan',
    };

    const RTL = new Set(['ar','fa','he','ur','yi']);

    // Allowed inline tags in translations (same set Vortex main app supports)
    const ALLOWED_TAGS = new Set(['STRONG', 'EM', 'BR', 'B', 'I', 'CODE']);

    let _currentLocale = DEFAULT_LOCALE;
    let _translations = {};
    let _fallback = {};

    function resolveKey(obj, keyPath) {
        const parts = keyPath.split('.');
        let cur = obj;
        for (const p of parts) {
            if (cur && typeof cur === 'object' && p in cur) cur = cur[p];
            else return null;
        }
        return cur;
    }

    function t(key) {
        return resolveKey(_translations, key)
            ?? resolveKey(_fallback, key)
            ?? key;
    }

    /** Safely populate `target` with `text` that may contain whitelisted inline tags. */
    function renderInline(target, text) {
        while (target.firstChild) target.removeChild(target.firstChild);
        if (typeof text !== 'string') return;
        if (!/[<>]/.test(text)) {
            target.textContent = text;
            return;
        }
        // Parse HTML through DOMParser (sandboxed — doesn't execute scripts).
        const doc = new DOMParser().parseFromString(
            `<body>${text}</body>`, 'text/html',
        );
        const body = doc.body;
        body.childNodes.forEach(n => target.appendChild(sanitize(n)));
    }

    function sanitize(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            return document.createTextNode(node.textContent || '');
        }
        if (node.nodeType !== Node.ELEMENT_NODE) {
            return document.createTextNode(node.textContent || '');
        }
        if (!ALLOWED_TAGS.has(node.tagName)) {
            return document.createTextNode(node.textContent || '');
        }
        const el = document.createElement(node.tagName.toLowerCase());
        node.childNodes.forEach(c => el.appendChild(sanitize(c)));
        return el;
    }

    function applyDom() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const val = t(el.dataset.i18n);
            if (typeof val !== 'string') return;
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                if (el.type === 'button' || el.type === 'submit') el.value = val;
                else el.placeholder = val;
                return;
            }
            renderInline(el, val);
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const val = t(el.dataset.i18nTitle);
            if (typeof val === 'string') el.setAttribute('title', val);
        });
        document.documentElement.lang = _currentLocale;
        document.documentElement.dir = RTL.has(_currentLocale) ? 'rtl' : 'ltr';
    }

    async function loadJson(code) {
        const r = await fetch(`/locales/${code}.json`, { cache: 'force-cache' });
        if (!r.ok) throw new Error(`locale ${code} not found`);
        return r.json();
    }

    async function setLocale(code) {
        if (!SUPPORTED.includes(code)) code = DEFAULT_LOCALE;
        try {
            _translations = await loadJson(code);
        } catch {
            _translations = {};
        }
        if (code !== DEFAULT_LOCALE && Object.keys(_fallback).length === 0) {
            try { _fallback = await loadJson(DEFAULT_LOCALE); } catch { _fallback = {}; }
        } else if (code === DEFAULT_LOCALE) {
            _fallback = _translations;
        }
        _currentLocale = code;
        try { localStorage.setItem(STORAGE_KEY, code); } catch {}
        applyDom();
        window.dispatchEvent(new CustomEvent('i18n:loaded', { detail: { locale: code } }));
    }

    function pickInitial() {
        let saved = null;
        try { saved = localStorage.getItem(STORAGE_KEY); } catch {}
        if (saved && SUPPORTED.includes(saved)) return saved;
        const nav = (navigator.language || 'en').toLowerCase();
        const short = nav.split('-')[0];
        if (SUPPORTED.includes(nav)) return nav;
        if (SUPPORTED.includes(short)) return short;
        return DEFAULT_LOCALE;
    }

    function buildLangMenu() {
        const menu = document.getElementById('lang-menu');
        const btn  = document.getElementById('lang-btn');
        const cur  = document.getElementById('lang-current');
        if (!menu || !btn || !cur) return;

        while (menu.firstChild) menu.removeChild(menu.firstChild);

        SUPPORTED.forEach(code => {
            const item = document.createElement('button');
            item.className = 'lang-item' + (code === _currentLocale ? ' active' : '');
            item.dataset.code = code;
            item.type = 'button';

            const name = document.createElement('span');
            name.className = 'lang-item-name';
            name.textContent = NAMES[code] || code;

            const codeEl = document.createElement('span');
            codeEl.className = 'lang-item-code';
            codeEl.textContent = code.toUpperCase();

            item.append(name, codeEl);
            item.addEventListener('click', async () => {
                await setLocale(code);
                cur.textContent = code.toUpperCase();
                menu.classList.remove('open');
                menu.querySelectorAll('.lang-item.active').forEach(e => e.classList.remove('active'));
                item.classList.add('active');
            });
            menu.appendChild(item);
        });

        btn.addEventListener('click', e => {
            e.stopPropagation();
            menu.classList.toggle('open');
        });
        document.addEventListener('click', e => {
            if (!menu.contains(e.target) && !btn.contains(e.target)) {
                menu.classList.remove('open');
            }
        });
        cur.textContent = _currentLocale.toUpperCase();
    }

    window.VortexI18n = { t, setLocale, applyDom, getLocale: () => _currentLocale };

    (async () => {
        const initial = pickInitial();
        await setLocale(initial);
        buildLangMenu();
    })();
})();
