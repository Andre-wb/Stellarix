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

    const hasAvatar = typeof Avatar !== 'undefined';

    function applyBubbleStyle(bubble, kind) {
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
    }

    function makeBubble(kind) {
        const bubble = document.createElement('div');
        bubble.classList.add('chat-bubble');
        applyBubbleStyle(bubble, kind);
        return bubble;
    }

    function peerName() {
        return hasAvatar ? Avatar.getPeerName() : '';
    }

    function makePeerAvatar() {
        const el = document.createElement('div');
        el.className = 'avatar-circle';
        if (hasAvatar) Avatar.render(el, Avatar.getPeer(), Avatar.peerLetter());
        else el.textContent = '?';
        return el;
    }

    function makePeerName() {
        const el = document.createElement('div');
        el.className = 'msg-name';
        el.textContent = peerName();
        return el;
    }

    function appendBubble(bubble, kind) {
        if (kind === 'received') {
            const row = document.createElement('div');
            row.className = 'msg-row received';
            bubble.style.alignSelf = 'auto';
            row.appendChild(makePeerAvatar());
            const col = document.createElement('div');
            col.className = 'msg-col';
            col.appendChild(makePeerName());
            col.appendChild(bubble);
            row.appendChild(col);
            messagesEl.appendChild(row);
        } else {
            messagesEl.appendChild(bubble);
        }
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function refreshPeerAvatars() {
        if (!hasAvatar) return;
        const peer = Avatar.getPeer();
        const name = peerName();
        messagesEl.querySelectorAll('.msg-row.received .avatar-circle').forEach((el) => {
            Avatar.render(el, peer, Avatar.peerLetter());
        });
        messagesEl.querySelectorAll('.msg-row.received .msg-name').forEach((el) => {
            el.textContent = name;
        });
    }

    function addMessage(text, kind) {
        const bubble = makeBubble(kind);
        bubble.textContent = text;
        appendBubble(bubble, kind);
    }

    function isImageName(name) {
        return /\.(png|jpe?g|webp|gif|bmp)$/i.test(name || '');
    }

    function isTextName(name) {
        return /\.(txt|md|csv|log|json)$/i.test(name || '');
    }

    function mimeForName(name) {
        const ext = ((name || '').split('.').pop() || '').toLowerCase();
        if (ext === 'json') return 'application/json';
        if (ext === 'pdf') return 'application/pdf';
        if (ext === 'txt' || ext === 'md' || ext === 'csv' || ext === 'log') return 'text/plain';
        return 'application/octet-stream';
    }

    function bytesToBase64(bytes) {
        let bin = '';
        const CHUNK = 0x8000;
        for (let i = 0; i < bytes.length; i += CHUNK) {
            bin += String.fromCharCode.apply(null, Array.prototype.slice.call(bytes, i, i + CHUNK));
        }
        return btoa(bin);
    }

    function bytesToImageUrl(bytes) {
        if (hasAvatar && typeof Avatar.bytesToDataUrl === 'function') return Avatar.bytesToDataUrl(bytes);
        return 'data:image/jpeg;base64,' + bytesToBase64(bytes);
    }

    function fileDataUrl(name, bytes) {
        return 'data:' + mimeForName(name) + ';base64,' + bytesToBase64(bytes);
    }

    function fileText(name, bytes) {
        if (!isTextName(name)) return null;
        try {
            return new TextDecoder('utf-8', { fatal: false }).decode(new Uint8Array(bytes));
        } catch (e) {
            return null;
        }
    }

    function fillFileCard(bubble, name, meta) {
        bubble.textContent = '';
        bubble.classList.add('chat-file');
        const title = document.createElement('div');
        title.textContent = ' ' + name;
        title.insertAdjacentHTML('afterbegin', StxIcons.clip);
        bubble.appendChild(title);
        if (meta) {
            const metaEl = document.createElement('div');
            metaEl.className = 'chat-file-meta';
            metaEl.textContent = meta;
            bubble.appendChild(metaEl);
        }
    }

    function addFileCard(name, meta, kind) {
        const bubble = makeBubble(kind);
        fillFileCard(bubble, name, meta);
        appendBubble(bubble, kind);
    }

    function openFileFromBytes(name, bytes) {
        window.openFileViewer(name || 'файл', fileDataUrl(name, bytes), fileText(name, bytes));
    }

    function makeOpenableCard(bubble, name, bytes, kind) {
        applyBubbleStyle(bubble, kind);
        fillFileCard(bubble, name || 'файл', formatSize(bytes.length));
        bubble.style.cursor = 'pointer';
        bubble.addEventListener('click', () => openFileFromBytes(name, bytes));
    }

    function addOpenableFile(name, bytes, kind) {
        const bubble = makeBubble(kind);
        makeOpenableCard(bubble, name, bytes, kind);
        appendBubble(bubble, kind);
    }

    function addImageMessage(name, bytes, kind) {
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble-media' + (kind === 'sent' ? ' own' : '');
        const img = document.createElement('img');
        img.className = 'chat-image';
        img.alt = name || '';
        img.loading = 'lazy';
        img.src = bytesToImageUrl(bytes);
        img.addEventListener('click', () => window.openImageViewer(img.src, name || ''));
        img.addEventListener('error', () => {
            bubble.className = 'chat-bubble';
            makeOpenableCard(bubble, name, bytes, kind);
        });
        bubble.appendChild(img);
        appendBubble(bubble, kind);
    }

    function addSentFile(name, bytes) {
        if (isImageName(name)) addImageMessage(name, bytes, 'sent');
        else addOpenableFile(name, bytes, 'sent');
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
            if (/^Доставлено/.test(report || '')) {
                setStatus('Сообщение доставлено — собеседник подтвердил получение.');
            } else if (report && !/остановлена/.test(report)) {
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

    async function runTransmit(name, bytes) {
        stopSendBtn.style.display = 'inline-block';
        const startedAt = Date.now();
        try {
            addSentFile(name, bytes);
            const keyHex = E2E.getSessionKeyHex();
            const report = await AudioModem.sendFile(name, AudioModem.bytesToHex(bytes), keyHex, setStatus);
            const delivered = /^Доставлено/.test(report || '');
            if (delivered) {
                setStatus('Файл доставлен — собеседник подтвердил получение.');
            } else if (report && !/остановлена|отменена/.test(report)) {
                setStatus(report + ' Убедитесь, что собеседник нажал «Слушать», и отправьте ещё раз.');
            }
            recordStats({ kind: 'tx', ok: delivered, bytes: bytes.length, ms: Date.now() - startedAt });
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
                await runTransmit(prepared.name, prepared.bytes);
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
                await runTransmit(file.name, bytes);
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
            await runTransmit(file.name, bytes);
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
                if (hasAvatar && Avatar.isUpdateHex(hex)) {
                    const profile = Avatar.profileFromUpdateHex(hex);
                    Avatar.setPeerName(profile.name);
                    Avatar.setPeer(profile.avatar);
                    refreshPeerAvatars();
                    setStatus('Собеседник обновил аватар.');
                    return;
                }
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
                if (info.saved && info.data_hex) {
                    const bytes = AudioModem.hexToBytes(info.data_hex);
                    if (isImageName(info.name)) {
                        addImageMessage(info.name, bytes, 'received');
                        setStatus('Изображение получено.');
                    } else {
                        addOpenableFile(info.name, bytes, 'received');
                        setStatus('Файл получен.');
                    }
                } else if (info.saved) {
                    addFileCard(info.name, formatSize(info.size), 'received');
                    setStatus('Файл получен.');
                } else {
                    addFileCard(info.name, info.reason || 'файл не сохранён', 'received');
                    setStatus('Файл не сохранён: ' + (info.reason || 'ошибка приёма.'));
                }
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
