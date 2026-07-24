document.addEventListener('DOMContentLoaded', () => {
    const shareBtn = document.getElementById('share-key-btn');
    const receiveBtn = document.getElementById('receive-key-btn');
    const stopBtn = document.getElementById('stop-key-btn');
    const resetBtn = document.getElementById('reset-key-btn');
    const statusEl = document.getElementById('pairing-status');
    const resultEl = document.getElementById('pairing-result');
    const levelEl = document.getElementById('mic-level');
    const bannerEl = document.getElementById('pairing-banner');
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

    function resetListenUi() {
        activeListener = null;
        receiveBtn.disabled = false;
        shareBtn.disabled = false;
        stopBtn.style.display = 'none';
    }

    function refreshBanner() {
        if (E2E.isPaired()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(40, 180, 99, 0.15)';
            bannerEl.innerHTML =
                '✅ Сопряжение выполнено. Отпечаток ключа: <strong>' + E2E.getFingerprint() + '</strong>. ' +
                'Сверьте его вслух с собеседником — если отпечатки совпадают, можно переходить в ' +
                '<a href="/chat">чат</a>.';
        } else if (E2E.hasPendingKey()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(230, 180, 30, 0.15)';
            bannerEl.textContent = '⏳ Ваш публичный ключ сгенерирован и готов к передаче, но сопряжение ещё не завершено (ключ собеседника не получен).';
        } else {
            bannerEl.style.display = 'none';
        }
    }

    if (!E2E.isSupported()) {
        setStatus('Этот браузер не поддерживает нужную криптографию (WebCrypto). Откройте сайт по адресу http://127.0.0.1:8000 в современном браузере.');
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
    }

    refreshBanner();

    shareBtn.addEventListener('click', async () => {
        if (activeListener) return;
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
        resultEl.textContent = '';
        try {
            setStatus('Генерирую ключ в браузере...');
            const publicHex = await E2E.ensureKeypair();
            setStatus('Передаю ключ...');
            await AudioModem.playPublicKeyHex(publicHex, setStatus);
            refreshBanner();
        } catch (err) {
            setStatus('Ошибка: ' + (err.message || err));
        } finally {
            shareBtn.disabled = false;
            receiveBtn.disabled = false;
        }
    });

    receiveBtn.addEventListener('click', () => {
        if (activeListener) return;
        receiveBtn.disabled = true;
        shareBtn.disabled = true;
        stopBtn.style.display = 'inline-block';
        resultEl.textContent = '';
        if (levelEl) levelEl.textContent = 'Уровень микрофона: [--------------------]';
        retryCount = 0;

        function startListeningCycle() {
            activeListener = AudioModem.startListening({
                onStatus: setStatus,
                onLevel: setLevel,
                onDecoded: async (hex) => {
                    const own = E2E.getPublicHex();
                    if (own && hex.toLowerCase() === own.toLowerCase()) {
                        activeListener = null;
                        setStatus('Пойман собственный ключ (эхо своего динамика) — продолжаю слушать собеседника...');
                        startListeningCycle();
                        return;
                    }
                    resetListenUi();
                    setStatus('Ключ получен, вычисляю общий сеансовый ключ в браузере...');
                    try {
                        const fingerprint = await E2E.completePairing(hex);
                        setStatus('Готово!');
                        resultEl.textContent =
                            'Сеансовый ключ создан в браузере. Сверьте отпечаток с собеседником вслух: ' + fingerprint;
                        refreshBanner();
                    } catch (err) {
                        setStatus('Ошибка: ' + err.message);
                        refreshBanner();
                        if (retryCount < MAX_RETRIES) {
                            retryCount++;
                            setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
                            setTimeout(startListeningCycle, 2000);
                        }
                    }
                },
                onError: (msg) => {
                    resetListenUi();
                    setStatus(msg);
                    if (retryCount < MAX_RETRIES) {
                        retryCount++;
                        setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
                        setTimeout(startListeningCycle, 2000);
                    }
                },
                onStopped: (msg) => {
                    resetListenUi();
                    setStatus(msg || 'Приём остановлен.');
                }
            });
        }

        startListeningCycle();
    });

    stopBtn.addEventListener('click', () => {
        if (!activeListener) return;
        setStatus('Останавливаю запись и анализирую...');
        activeListener.stop();
    });

    resetBtn.addEventListener('click', () => {
        if (!confirm('Точно начать сопряжение заново? Текущий сеансовый ключ (если есть) будет забыт.')) return;
        E2E.reset();
        setStatus('Сопряжение сброшено. Можно начинать заново.');
        resultEl.textContent = '';
        refreshBanner();
    });
});
