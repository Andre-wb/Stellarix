// Stellarix — переключение языка интерфейса (ru/en).
// Работает без правок существующих шаблонов: элементы находятся по ссылкам и id,
// новые страницы могут использовать data-i18n.
const StxI18n = (() => {
    var KEY = 'stx_lang';

    var NAV = {
        '/pairing': 'Pairing',
        '/chat': 'Chat',
        '/dashboard': 'Dashboard',
        '/profile': 'Profile',
        '/settings': 'Settings',
        '/logout': 'Log out',
        '/login': 'Log in',
        '/register': 'Sign up',
    };

    var IDS = {
        'listen-btn': 'Listen',
        'stop-listen-btn': 'Stop & decode',
        'stop-send-btn': 'Cancel sending',
    };

    var PLACEHOLDERS = {
        'username': 'Name',
        'password': 'Password',
        'confirm_password': 'Repeat password',
        'chat-input': 'Message (up to 68 bytes)...',
    };

    var KEYS = {
        'settings.title': 'Settings',
        'settings.theme': 'Theme',
        'settings.theme.dark': 'Dark',
        'settings.theme.light': 'Light',
        'settings.theme.auto': 'System',
        'settings.theme.hint': 'The theme is saved on this device and applied instantly.',
        'settings.language': 'Language',
        'settings.language.hint': 'Switches the interface language. Stored on this device.',
        'settings.transfer': 'Chats export & import',
        'settings.export': 'Export chats',
        'settings.import': 'Import chats',
        'settings.stub': 'This feature is in development and will arrive in a future update.',
        'auth.join': 'Join us',
        'auth.welcome': 'Welcome back',
        'auth.create': 'Create account',
        'auth.loginBtn': 'Log in',
        'auth.haveAccount': 'Already have an account?',
        'auth.loginLink': 'Log in',
        'auth.noAccount': "Don't have an account yet?",
        'auth.registerLink': 'Sign up',
    };

    function get() {
        try { return localStorage.getItem(KEY) || 'ru'; } catch (e) { return 'ru'; }
    }

    function setText(el, en) {
        if (el.dataset.i18nRu === undefined) el.dataset.i18nRu = el.textContent;
        el.textContent = (get() === 'en') ? en : el.dataset.i18nRu;
    }

    function apply() {
        var en = get() === 'en';
        document.querySelectorAll('a.nav-link').forEach(function (a) {
            var t = NAV[a.getAttribute('href')];
            if (t) setText(a, t);
        });
        Object.keys(IDS).forEach(function (id) {
            var el = document.getElementById(id);
            if (el) setText(el, IDS[id]);
        });
        Object.keys(PLACEHOLDERS).forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            if (el.dataset.i18nRuPh === undefined) el.dataset.i18nRuPh = el.getAttribute('placeholder') || '';
            el.setAttribute('placeholder', en ? PLACEHOLDERS[id] : el.dataset.i18nRuPh);
        });
        document.querySelectorAll('[data-i18n]').forEach(function (el) {
            var t = KEYS[el.getAttribute('data-i18n')];
            if (t) setText(el, t);
        });
        document.querySelectorAll('.lang-option').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-lang') === get());
        });
        document.documentElement.lang = get();
    }

    function set(lang) {
        try { localStorage.setItem(KEY, lang === 'en' ? 'en' : 'ru'); } catch (e) {}
        apply();
    }

    document.addEventListener('click', function (e) {
        var b = e.target && e.target.closest ? e.target.closest('.lang-option') : null;
        if (!b) return;
        set(b.getAttribute('data-lang'));
        b.blur();
    });

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply);
    else apply();

    return { get: get, set: set, apply: apply };
})();
