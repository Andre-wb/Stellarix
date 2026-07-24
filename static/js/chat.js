document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const listenBtn = document.getElementById('listen-btn');
    const stopListenBtn = document.getElementById('stop-listen-btn');
    const messagesEl = document.getElementById('chat-messages');
    const statusEl = document.getElementById('chat-status');
    const levelEl = document.getElementById('mic-level');
    const bannerEl = document.getElementById('chat-banner');
    let activeListener = null;
    let retryCount = 0;
    const MAX_RETRIES = 3;

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

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value;
        if (!text) return;

        sendBtn.disabled = true;
        try {
            setStatus('Шифрую сообщение в браузере...');
            const payloadHex = await E2E.encrypt(text);
            addMessage(text, 'sent');
            input.value = '';
            setStatus('Передаю сообщение (1/2)...');
            await AudioModem.playHexPayload(payloadHex, setStatus);
            await new Promise(r => setTimeout(r, 300));
            setStatus('Передаю сообщение (2/2)...');
            await AudioModem.playHexPayload(payloadHex, setStatus);
            setStatus('Сообщение передано.');
        } catch (err) {
            setStatus('Ошибка: ' + err.message);
        } finally {
            sendBtn.disabled = false;
        }
    });

    function resetListenUi() {
        activeListener = null;
        listenBtn.disabled = false;
        stopListenBtn.style.display = 'none';
        retryCount = 0;
    }

    function startListenCycle() {
        if (activeListener) return;
        listenBtn.disabled = true;
        stopListenBtn.style.display = 'inline-block';
        if (levelEl) levelEl.textContent = 'Уровень микрофона: [--------------------]';
        retryCount = 0;

        activeListener = AudioModem.startListening({
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
