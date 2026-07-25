document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const listenBtn = document.getElementById('listen-btn');
    const stopListenBtn = document.getElementById('stop-listen-btn');
    const stopSendBtn = document.getElementById('stop-send-btn');
    const attachBtn = document.getElementById('attach-btn');
    const fileInput = document.getElementById('file-input');
    const messagesEl = document.getElementById('chat-messages');
    const statusEl = document.getElementById('chat-status');
    const levelEl = document.getElementById('mic-level');
    const bannerEl = document.getElementById('chat-banner');
    const nativeReady = AudioModem.isAvailable();
    let activeListener = null;
    let retryCount = 0;
    let sending = false;
    const MAX_RETRIES = 3;
    const MAX_FILE_BYTES = 64 * 1024;
    const MAX_RAW_BYTES = 8 * 1024 * 1024;

    if (fileInput && typeof FilePolicy !== 'undefined') fileInput.accept = FilePolicy.accept();

    function setStatus(text) {
        statusEl.textContent = text;
    }

    function setLevel(rms) {
        if (!levelEl) return;
        const bars = Math.max(0, Math.min(20, Math.round(rms * 250)));
        levelEl.textContent = 'Уровень микрофона: [' + '#'.repeat(bars) + '-'.repeat(20 - bars) + ']';
    }

    function makeBubble(kind) {
        const bubble = document.createElement('div');
        bubble.style.padding = '0.5rem 0.75rem';
        bubble.style.borderRadius = '10px';
        bubble.style.maxWidth = '75%';
        bubble.style.wordBreak = 'break-word';
        if (kind === 'sent') {
            bubble.style.alignSelf = 'flex-end';
            bubble.style.background = 'var(--accent, #4a7dff)';
            bubble.style.color = '#fff';
        } else if (kind === 'received') {
            bubble.style.alignSelf = 'flex-start';
            bubble.style.background = 'rgba(120,120,120,0.2)';
        } else {
            bubble.style.alignSelf = 'center';
            bubble.style.fontSize = '0.8rem';
            bubble.style.opacity = '0.7';
            bubble.style.background = 'transparent';
        }
        return bubble;
    }

    function appendBubble(bubble) {
        messagesEl.appendChild(bubble);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function addMessage(text, kind) {
        const bubble = makeBubble(kind);
        bubble.textContent = text;
        appendBubble(bubble);
    }

    function addFileMessage(name, meta, kind) {
        const bubble = makeBubble(kind);
        bubble.classList.add('chat-file');
        const title = document.createElement('div');
        title.textContent = ' ' + name;
        title.insertAdjacentHTML('afterbegin', StxIcons.clip);
        const metaEl = document.createElement('div');
        metaEl.className = 'chat-file-meta';
        metaEl.textContent = meta;
        bubble.appendChild(title);
        bubble.appendChild(metaEl);
        appendBubble(bubble);
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' Б';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КиБ';
        return (bytes / (1024 * 1024)).toFixed(1) + ' МиБ';
    }

    function recordStats(session) {
        if (typeof StxStats !== 'undefined') StxStats.record(session);
    }

    function lockAudioUi() {
        bannerEl.style.display = 'block';
        bannerEl.style.background = 'rgba(230, 80, 60, 0.15)';
        bannerEl.innerHTML = StxIcons.warn + ' ' + AudioModem.unavailableReason;
        sendBtn.disabled = true;
        attachBtn.disabled = true;
        listenBtn.disabled = true;
        input.disabled = true;
        stopListenBtn.style.display = 'none';
        stopSendBtn.style.display = 'none';
        setStatus('Аудиоканал недоступен в браузере.');
    }

    function checkPairing() {
        if (!nativeReady) {
            lockAudioUi();
            return;
        }
        if (!E2E.isSupported()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(230, 80, 60, 0.15)';
            bannerEl.innerHTML = StxIcons.warn + ' Встроенный движок приложения не поддерживает нужную криптографию (WebCrypto). Обновите систему или компонент WebView.';
            sendBtn.disabled = true;
            return;
        }
        if (!E2E.isPaired()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(230, 80, 60, 0.15)';
            bannerEl.innerHTML = StxIcons.warn + ' Сопряжение ещё не выполнено. <a href="/pairing">Выполните сопряжение по звуку</a> перед началом чата.';
            sendBtn.disabled = true;
        } else {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(40, 180, 99, 0.15)';
            bannerEl.innerHTML = StxIcons.ok + ' Сопряжено. Отпечаток ключа: ' + E2E.getFingerprint();
            sendBtn.disabled = false;
        }
    }

    checkPairing();

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value;
        if (!text || sending || !nativeReady) return;

        sending = true;
        sendBtn.disabled = true;
        attachBtn.disabled = true;
        try {
            setStatus('Шифрую сообщение в браузере...');
            const payloadHex = await E2E.encrypt(text);
            addMessage(text, 'sent');
            input.value = '';
            setStatus('Передаю сообщение...');
            const report = await AudioModem.playHexPayload(payloadHex, setStatus);
            if (AudioModem.wasDelivered(report)) {
                setStatus('Сообщение доставлено — собеседник подтвердил получение.');
            } else if (report && !AudioModem.wasStopped(report)) {
                setStatus(report + ' Убедитесь, что собеседник нажал «Слушать», и отправьте ещё раз.');
            }
        } catch (err) {
            setStatus('Ошибка: ' + err.message);
        } finally {
            sending = false;
            attachBtn.disabled = false;
            sendBtn.disabled = false;
        }
    });

    attachBtn.addEventListener('click', () => {
        if (sending || !nativeReady) return;
        fileInput.click();
    });

    async function runTransmit(name, bytes, metaLabel) {
        stopSendBtn.style.display = 'inline-block';
        const startedAt = Date.now();
        try {
            addFileMessage(name, metaLabel, 'sent');
            const keyHex = E2E.getSessionKeyHex();
            const ok = await AudioModem.sendFile(name, AudioModem.bytesToHex(bytes), keyHex, setStatus);
            recordStats({ kind: 'tx', ok: ok, bytes: bytes.length, ms: Date.now() - startedAt });
        } catch (err) {
            setStatus('Ошибка: ' + err.message);
            recordStats({ kind: 'tx', ok: false, bytes: bytes.length, ms: Date.now() - startedAt });
        } finally {
            stopSendBtn.style.display = 'none';
        }
    }

    fileInput.addEventListener('change', async () => {
        const file = fileInput.files && fileInput.files[0];
        fileInput.value = '';
        if (!file || sending || !nativeReady) return;
        if (file.size === 0) {
            setStatus('Файл пуст — нечего передавать.');
            return;
        }
        if (!E2E.isPaired()) {
            setStatus('Сначала выполните сопряжение по звуку — без него файл не зашифровать.');
            return;
        }

        sending = true;
        attachBtn.disabled = true;
        sendBtn.disabled = true;
        try {
            if (ImageCompress.isImage(file)) {
                setStatus('Изображение — открываю сжатие для передачи звуком...');
                const prepared = await AttachImage.open(file, {
                    maxBytes: MAX_FILE_BYTES,
                });
                if (!prepared) {
                    setStatus('Отправка отменена.');
                    return;
                }
                setStatus('Готовлю сжатое изображение к передаче...');
                await runTransmit(prepared.name, prepared.bytes, prepared.meta);
                return;
            }

            if (FilePolicy.hasDangerousDoubleExtension(file.name)) {
                setStatus('Отклонено: подозрительное двойное расширение в имени файла.');
                return;
            }
            if (!FilePolicy.isAllowed(file.name)) {
                setStatus('Формат «.' + FilePolicy.extOf(file.name) + '» не разрешён к передаче. ' +
                    'Разрешены: ' + FilePolicy.list() + '.');
                return;
            }
            if (file.size <= MAX_FILE_BYTES) {
                setStatus('Готовлю файл к передаче...');
                const bytes = new Uint8Array(await file.arrayBuffer());
                await runTransmit(file.name, bytes, formatSize(file.size) + ' · зашифровано E2E');
                return;
            }
            if (file.size > MAX_RAW_BYTES) {
                setStatus('Файл слишком большой: ' + formatSize(file.size) +
                    ' — даже со сжатием не поместится (потолок ' + formatSize(MAX_RAW_BYTES) + ').');
                return;
            }
            if (typeof FileCompress === 'undefined' || !FileCompress.supported()) {
                setStatus('Файл слишком большой: максимум ' + formatSize(MAX_FILE_BYTES) +
                    ', у вас ' + formatSize(file.size) + '.');
                return;
            }
            setStatus('Оцениваю сжатие (' + formatSize(file.size) + ')...');
            let est;
            try {
                est = await FileCompress.estimate(file);
            } catch (e) {
                setStatus('Файл слишком большой: максимум ' + formatSize(MAX_FILE_BYTES) +
                    ', у вас ' + formatSize(file.size) + '.');
                return;
            }
            if (est.compressed > MAX_FILE_BYTES) {
                setStatus('Не поместится даже после сжатия: ' + formatSize(file.size) +
                    ' → ~' + formatSize(est.compressed) + ' (лимит ' + formatSize(MAX_FILE_BYTES) + ').');
                return;
            }
            setStatus('Файл ' + formatSize(file.size) + ' → ~' + formatSize(est.compressed) +
                ' после сжатия — отправляю...');
            const bytes = new Uint8Array(await file.arrayBuffer());
            const meta = formatSize(file.size) + ' → ~' + formatSize(est.compressed) +
                ' · сжатие · зашифровано E2E';
            await runTransmit(file.name, bytes, meta);
        } catch (err) {
            setStatus('Ошибка: ' + err.message);
        } finally {
            sending = false;
            attachBtn.disabled = false;
            checkPairing();
        }
    });

    stopSendBtn.addEventListener('click', () => {
        if (!sending) return;
        setStatus('Останавливаю передачу...');
        AudioModem.stopPlaying();
    });

    function resetListenUi() {
        activeListener = null;
        listenBtn.disabled = false;
        stopListenBtn.style.display = 'none';
        retryCount = 0;
    }

    function startListenCycle() {
        if (activeListener || !nativeReady) return;
        listenBtn.disabled = true;
        stopListenBtn.style.display = 'inline-block';
        if (levelEl) levelEl.textContent = 'Уровень микрофона: [--------------------]';
        retryCount = 0;

        activeListener = AudioModem.startListening({
            key: E2E.getSessionKeyHex(),
            onStatus: setStatus,
            onLevel: setLevel,
            onDecoded: async (hex) => {
                resetListenUi();
                setStatus('Сигнал получен, расшифровываю в браузере...');
                try {
                    const plaintext = await E2E.decrypt(hex);
                    addMessage(plaintext, 'received');
                    setStatus('Сообщение получено.');
                } catch (err) {
                    setStatus('Ошибка расшифровки: ' + err.message);
                    if (nativeReady && retryCount < MAX_RETRIES) {
                        retryCount++;
                        setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
                        setTimeout(startListenCycle, 2000);
                    }
                }
            },
            onFile: (info) => {
                resetListenUi();
                const meta = info.saved
                    ? formatSize(info.size) + ' · E2E · SHA-256 совпала · ' + info.path
                    : formatSize(info.size) + ' · ' + (info.reason || 'файл не сохранён');
                addFileMessage(info.name, meta, 'received');
                setStatus(info.saved
                    ? 'Файл получен и сохранён.'
                    : 'Файл не сохранён: ' + (info.reason || 'ошибка приёма.'));
                recordStats({ kind: 'rx', ok: info.saved, bytes: info.size });
            },
            onError: (msg) => {
                resetListenUi();
                setStatus(msg);
                if (nativeReady && retryCount < MAX_RETRIES) {
                    retryCount++;
                    setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
                    setTimeout(startListenCycle, 2000);
                }
            },
            onStopped: (msg) => {
                resetListenUi();
                setStatus(msg);
            }
        });
    }

    listenBtn.addEventListener('click', startListenCycle);

    stopListenBtn.addEventListener('click', () => {
        if (!activeListener) return;
        setStatus('Останавливаю запись и анализирую...');
        activeListener.stop();
    });
});
