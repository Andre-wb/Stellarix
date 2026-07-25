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

    var settingsBox = document.getElementById('avatar-settings');
    var preview = document.getElementById('avatar-preview');
    var fileInput = document.getElementById('avatar-file');
    var changeBtn = document.getElementById('avatar-change-btn');
    var removeBtn = document.getElementById('avatar-remove-btn');
    var avatarStatus = document.getElementById('avatar-status');

    if (settingsBox && preview && typeof Avatar !== 'undefined') {
        var username = settingsBox.getAttribute('data-username') || '';
        var syncing = false;

        function setAvatarStatus(text) { if (avatarStatus) avatarStatus.textContent = text; }

        function refreshAvatar() {
            var own = Avatar.getOwn();
            Avatar.render(preview, own, Avatar.letter(username));
            if (removeBtn) removeBtn.hidden = !own;
        }

        function syncToPeer() {
            if (typeof E2E === 'undefined' || typeof AudioModem === 'undefined') return Promise.resolve();
            if (!AudioModem.isAvailable()) { setAvatarStatus('Сохранено на этом устройстве.'); return Promise.resolve(); }
            if (!E2E.isPaired()) { setAvatarStatus('Сохранено на устройстве. Сопряжения нет — отправить собеседнику нельзя.'); return Promise.resolve(); }
            if (syncing) return Promise.resolve();
            syncing = true;
            setAvatarStatus('Отправляю аватар собеседнику по звуку — он должен слушать в чате...');
            return AudioModem.playHexPayload(Avatar.updateMsgHex(), setAvatarStatus)
                .then(function (report) {
                    if (/^Доставлено/.test(report || '')) setAvatarStatus('Аватар доставлен — собеседник подтвердил.');
                    else if (report && !/остановлена/.test(report)) setAvatarStatus('Похоже, собеседник не слушал. Откройте у него чат, нажмите «Слушать» и повторите.');
                })
                .catch(function (e) { setAvatarStatus('Ошибка отправки: ' + e.message); })
                .then(function () { syncing = false; });
        }

        function acceptAvatar(file) {
            if (!file) return;
            if (!Avatar.isImageFile(file)) { setAvatarStatus('Это не изображение — выберите png, jpg или webp.'); return; }
            setAvatarStatus('Обрабатываю фото...');
            Avatar.compressFile(file)
                .then(function (dataUrl) {
                    Avatar.setOwn(dataUrl);
                    refreshAvatar();
                    return syncToPeer();
                })
                .catch(function (e) { setAvatarStatus('Не удалось обработать фото: ' + e.message); });
        }

        refreshAvatar();

        if (changeBtn) changeBtn.addEventListener('click', function () { fileInput.click(); });
        preview.addEventListener('click', function () { fileInput.click(); });
        fileInput.addEventListener('change', function () {
            var f = fileInput.files && fileInput.files[0];
            fileInput.value = '';
            acceptAvatar(f);
        });

        ['dragenter', 'dragover'].forEach(function (ev) {
            settingsBox.addEventListener(ev, function (e) { e.preventDefault(); settingsBox.classList.add('dragover'); });
        });
        ['dragleave', 'dragend'].forEach(function (ev) {
            settingsBox.addEventListener(ev, function () { settingsBox.classList.remove('dragover'); });
        });
        settingsBox.addEventListener('drop', function (e) {
            e.preventDefault();
            settingsBox.classList.remove('dragover');
            var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            acceptAvatar(f);
        });

        if (removeBtn) {
            removeBtn.addEventListener('click', function () {
                Avatar.clearOwn();
                refreshAvatar();
                syncToPeer();
            });
        }
    }
})();
