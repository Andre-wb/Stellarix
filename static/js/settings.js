// Stellarix — страница настроек: тема (в т.ч. «как в системе»), язык, заглушка экспорта/импорта.
(function () {
    var THEME_KEY = 'stx_theme';
    var themeBtns = Array.prototype.slice.call(document.querySelectorAll('.theme-option'));
    var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

    function storedPref() {
        try { return localStorage.getItem(THEME_KEY) || 'dark'; } catch (e) { return 'dark'; }
    }

    // 'auto' → текущая системная тема (Windows / Linux / macOS — через prefers-color-scheme)
    function resolve(pref) {
        if (pref === 'auto') return (mq && mq.matches) ? 'light' : 'dark';
        return pref;
    }

    function setDom(theme) {
        if (theme === 'dark') document.documentElement.removeAttribute('data-theme');
        else document.documentElement.setAttribute('data-theme', theme);
    }

    function applyTheme(pref) {
        try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}
        setDom(resolve(pref));
        themeBtns.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-theme-value') === pref); });
    }

    themeBtns.forEach(function (b) {
        b.addEventListener('click', function () {
            applyTheme(b.getAttribute('data-theme-value'));
            b.blur();
        });
        b.classList.toggle('active', b.getAttribute('data-theme-value') === storedPref());
    });

    // Живая реакция на смену системной темы в режиме «как в системе»
    if (mq) {
        var onSystemChange = function () {
            if (storedPref() === 'auto') setDom(resolve('auto'));
        };
        if (mq.addEventListener) mq.addEventListener('change', onSystemChange);
        else if (mq.addListener) mq.addListener(onSystemChange);
    }

    // Переключатель языка (пилюля)
    var langBtns = Array.prototype.slice.call(document.querySelectorAll('.lang-option'));

    function syncLang() {
        var cur = (typeof StxI18n !== 'undefined') ? StxI18n.get() : 'ru';
        langBtns.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-lang') === cur); });
    }

    langBtns.forEach(function (b) {
        b.addEventListener('click', function () {
            if (typeof StxI18n !== 'undefined') StxI18n.set(b.getAttribute('data-lang'));
            syncLang();
            b.blur();
        });
    });
    syncLang();

    // Заглушка экспорта/импорта чатов
    var stub = document.getElementById('transfer-stub');
    ['export-chats-btn', 'import-chats-btn'].forEach(function (id) {
        var b = document.getElementById(id);
        if (!b) return;
        b.addEventListener('click', function () {
            if (stub) stub.style.display = 'block';
        });
    });
})();
