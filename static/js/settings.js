// Stellarix — страница настроек: тема, язык, заглушка экспорта/импорта чатов.
(function () {
    var THEME_KEY = 'stx_theme';
    var themeBtns = Array.prototype.slice.call(document.querySelectorAll('.theme-option'));

    function currentTheme() {
        try { return localStorage.getItem(THEME_KEY) || 'dark'; } catch (e) { return 'dark'; }
    }

    function applyTheme(theme) {
        if (theme === 'dark') document.documentElement.removeAttribute('data-theme');
        else document.documentElement.setAttribute('data-theme', theme);
        try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
        themeBtns.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-theme-value') === theme); });
    }

    themeBtns.forEach(function (b) {
        b.addEventListener('click', function () { applyTheme(b.getAttribute('data-theme-value')); });
        b.classList.toggle('active', b.getAttribute('data-theme-value') === currentTheme());
    });

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
