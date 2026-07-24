document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const fileBtn = document.getElementById('send-file-btn');
    const fileInput = document.getElementById('file-input');
    const listenBtn = document.getElementById('listen-btn');
    const stopListenBtn = document.getElementById('stop-listen-btn');
    const messagesEl = document.getElementById('chat-messages');
    const statusEl = document.getElementById('chat-status');
    const levelEl = document.getElementById('mic-level');
    const bannerEl = document.getElementById('chat-banner');
    const modulationEl = document.getElementById('modulation-select');
    let activeListener = null;
    let retryCount = 0;
    let chatId = null;
    const MAX_RETRIES = 3;

    function currentModulation() {
        return modulationEl ? modulationEl.value : undefined;
    }

    function setStatus(text) {
        statusEl.textContent = text;
    }

    function setLevel(rms) {
        if (!levelEl) return;
        const bars = Math.max(0, Math.min(20, Math.round(rms * 250)));
        levelEl.textContent = 'Уровень микрофона: [' + '#'.repeat(bars) + '-'.repeat(20 - bars) + ']';
    }

    function addMessage(text, kind) {
        const bubble = document.createElement('div');
        bubble.textContent = text;
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
        messagesEl.appendChild(bubble);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function checkPairing() {
        if (!E2E.isSupported()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(230, 80, 60, 0.15)';
            bannerEl.textContent = '⚠️ Этот браузер не поддерживает нужную криптографию (WebCrypto).';
            sendBtn.disabled = true;
            return;
        }
        if (!E2E.isPaired()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(230, 80, 60, 0.15)';
            bannerEl.innerHTML = '⚠️ Сопряжение ещё не выполнено. <a href="/pairing">Выполните сопряжение по звуку</a> перед началом чата.';
            sendBtn.disabled = true;
        } else {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(40, 180, 99, 0.15)';
            bannerEl.textContent = '✅ Сопряжено. Отпечаток ключа: ' + E2E.getFingerprint();
            sendBtn.disabled = false;
        }
    }

    checkPairing();

    async function loadHistory() {
        if (!E2E.isSupported() || !E2E.isPaired()) return;
        try {
            const chatRes = await fetch('/api/chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ peer_fingerprint: E2E.getFingerprint() }),
            });
            if (!chatRes.ok) return;
            chatId = (await chatRes.json()).id;

            const msgRes = await fetch('/api/chats/' + chatId + '/messages');
            if (!msgRes.ok) return;
            const messages = await msgRes.json();
            let failed = 0;
            for (const m of messages) {
                try {
                    const text = await E2E.decrypt(m.payload_hex);
                    addMessage(text, m.outgoing ? 'sent' : 'received');
                } catch (err) {
                    failed++;
                }
            }
            if (failed > 0) {
                addMessage('Не удалось расшифровать сохранённых сообщений: ' + failed, 'info');
            }
        } catch (err) {
            console.warn('Не удалось загрузить историю чата:', err);
        }
    }

    function saveMessage(payloadHex, outgoing) {
        if (!chatId) return;
        fetch('/api/chats/' + chatId + '/messages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payload_hex: payloadHex, outgoing }),
        }).catch((err) => console.warn('Не удалось сохранить сообщение:', err));
    }

    loadHistory();

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value;
        if (!text) return;
        if (activeListener) return;

        sendBtn.disabled = true;
        listenBtn.disabled = true;
        fileBtn.disabled = true;
        try {
            setStatus('Шифрую сообщение в браузере...');
            const payloadHex = await E2E.encrypt(text);
            addMessage(text, 'sent');
            saveMessage(payloadHex, true);
            input.value = '';
            await AudioModem.sendHexPayload(payloadHex, setStatus, currentModulation());
        } catch (err) {
            setStatus('Ошибка: ' + (err.message || err));
        } finally {
            sendBtn.disabled = false;
            listenBtn.disabled = false;
            fileBtn.disabled = false;
        }
    });

    function formatSize(n) {
        if (n < 1024) return n + ' Б';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' КБ';
        return (n / (1024 * 1024)).toFixed(1) + ' МБ';
    }

    fileBtn.addEventListener('click', () => {
        if (activeListener) return;
        fileInput.click();
    });

    fileInput.addEventListener('change', async () => {
        const file = fileInput.files && fileInput.files[0];
        fileInput.value = '';
        if (!file || activeListener) return;
        if (file.size > 4 * 1024 * 1024) {
            setStatus('Файл больше 4 МБ — для звукового канала это слишком много.');
            return;
        }
        const estSec = Math.max(3, Math.round(file.size / 700));
        if (estSec > 30 && !confirm(
            `Передача файла «${file.name}» (${formatSize(file.size)}) займёт примерно ` +
            `${Math.ceil(estSec / 60)} мин. Продолжить?`)) return;
        sendBtn.disabled = true;
        listenBtn.disabled = true;
        fileBtn.disabled = true;
        try {
            const buf = new Uint8Array(await file.arrayBuffer());
            let hex = '';
            for (let i = 0; i < buf.length; i += 4096) {
                hex += Array.from(buf.subarray(i, i + 4096), b => b.toString(16).padStart(2, '0')).join('');
            }
            addMessage(`📎 Отправка файла: ${file.name} (${formatSize(file.size)})`, 'sent');
            const result = await AudioModem.sendFileHex(file.name, hex, setStatus, currentModulation());
            addMessage(`📎 ${file.name}: ${result}`, 'info');
        } catch (err) {
            setStatus('Ошибка: ' + (err.message || err));
        } finally {
            sendBtn.disabled = !E2E.isPaired();
            listenBtn.disabled = false;
            fileBtn.disabled = false;
        }
    });

    function resetListenUi() {
        activeListener = null;
        listenBtn.disabled = false;
        sendBtn.disabled = !E2E.isPaired();
        fileBtn.disabled = false;
        stopListenBtn.style.display = 'none';
    }

    function startListenCycle() {
        if (activeListener) return;
        listenBtn.disabled = true;
        sendBtn.disabled = true;
        fileBtn.disabled = true;
        stopListenBtn.style.display = 'inline-block';
        if (levelEl) levelEl.textContent = 'Уровень микрофона: [--------------------]';

        activeListener = AudioModem.startListening({
            onStatus: setStatus,
            onLevel: setLevel,
            onFile: (f) => {
                resetListenUi();
                const ok = f.hash_ok ? 'хеш SHA-256 совпал ✅' : 'ХЕШ SHA-256 НЕ СОВПАЛ ❌';
                addMessage(`📎 Получен файл ${f.name} (${formatSize(f.size)}) — ${ok}. Сохранён: ${f.path}`, 'received');
                setStatus('Файл получен.');
            },
            onDecoded: async (hex) => {
                resetListenUi();
                setStatus('Сигнал получен, расшифровываю в браузере...');
                try {
                    const plaintext = await E2E.decrypt(hex);
                    addMessage(plaintext, 'received');
                    saveMessage(hex, false);
                    setStatus('Сообщение получено.');
                } catch (err) {
                    setStatus('Ошибка расшифровки: ' + err.message);
                    if (retryCount < MAX_RETRIES) {
                        retryCount++;
                        setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
                        setTimeout(startListenCycle, 2000);
                    }
                }
            },
            onError: (msg) => {
                resetListenUi();
                setStatus(msg);
                if (retryCount < MAX_RETRIES) {
                    retryCount++;
                    setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
                    setTimeout(startListenCycle, 2000);
                }
            },
            onStopped: (msg) => {
                resetListenUi();
                setStatus(msg || 'Приём остановлен.');
            }
        });
    }

    listenBtn.addEventListener('click', () => {
        retryCount = 0;
        startListenCycle();
    });

    stopListenBtn.addEventListener('click', () => {
        if (!activeListener) return;
        setStatus('Останавливаю запись и анализирую...');
        activeListener.stop();
    });
});
