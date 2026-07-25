document.addEventListener('DOMContentLoaded', () => {
    const shareBtn = document.getElementById('share-key-btn');
    const receiveBtn = document.getElementById('receive-key-btn');
    const stopBtn = document.getElementById('stop-key-btn');
    const resetBtn = document.getElementById('reset-key-btn');
    const statusEl = document.getElementById('pairing-status');
    const resultEl = document.getElementById('pairing-result');
    const levelEl = document.getElementById('mic-level');
    const bannerEl = document.getElementById('pairing-banner');
    const nativeReady = AudioModem.isAvailable();
    let activeListener = null;
    let retryCount = 0;
    let retryTimer = null;
    let sharing = false;
    let shareGen = 0;
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

    function scheduleRetry(startFn) {
        if (!nativeReady || retryCount >= MAX_RETRIES) return;
        retryCount++;
        setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
        retryTimer = setTimeout(() => { retryTimer = null; startFn(); }, 2000);
    }

    function cancelActivity() {
        shareGen++;
        sharing = false;
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        if (activeListener) activeListener.cancel();
        resetListenUi();
        retryCount = 0;
        AudioModem.stopPlaying();
    }

    function lockAudioUi() {
        bannerEl.style.display = 'block';
        bannerEl.style.background = 'rgba(230, 80, 60, 0.15)';
        bannerEl.innerHTML = StxIcons.warn + ' ' + AudioModem.unavailableReason;
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
        resetBtn.disabled = true;
        stopBtn.style.display = 'none';
        setStatus('Аудиоканал недоступен в браузере.');
    }

    function refreshBanner() {
        if (!nativeReady) {
            lockAudioUi();
            return;
        }
        if (E2E.isPaired()) {
            bannerEl.style.display = 'block';
            bannerEl.style.background = 'rgba(40, 180, 99, 0.15)';
            bannerEl.innerHTML =
                StxIcons.ok + ' Сопряжение выполнено. Отпечаток ключа: <strong>' + E2E.getFingerprint() + '</strong>. ' +
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
        setStatus('Встроенный движок приложения не поддерживает нужную криптографию (WebCrypto). Обновите систему или компонент WebView — без него сопряжение невозможно.');
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
    }

    refreshBanner();

    shareBtn.addEventListener('click', async () => {
        if (activeListener || sharing || !nativeReady) return;
        const gen = ++shareGen;
        sharing = true;
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
        resultEl.textContent = '';
        try {
            setStatus('Генерирую ключ в браузере...');
            const publicHex = await E2E.ensureKeypair();
            if (gen !== shareGen) return;
            setStatus('Передаю ключ (1/2)...');
            await AudioModem.playPublicKeyHex(publicHex, setStatus);
            if (gen !== shareGen) return;
            await new Promise(r => setTimeout(r, 500));
            if (gen !== shareGen) return;
            setStatus('Передаю ключ (2/2)...');
            await AudioModem.playPublicKeyHex(publicHex, setStatus);
            if (gen !== shareGen) return;
            refreshBanner();
        } catch (err) {
            if (gen === shareGen) setStatus('Ошибка: ' + err.message);
        } finally {
            if (gen === shareGen) {
                sharing = false;
                shareBtn.disabled = false;
                receiveBtn.disabled = false;
            }
        }
    });

    receiveBtn.addEventListener('click', () => {
        if (activeListener || sharing || !nativeReady) return;
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        resultEl.textContent = '';
        if (levelEl) levelEl.textContent = 'Уровень микрофона: [--------------------]';
        retryCount = 0;

        function startListeningCycle() {
            receiveBtn.disabled = true;
            shareBtn.disabled = true;
            stopBtn.style.display = 'inline-block';
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
                        scheduleRetry(startListeningCycle);
                    }
                },
                onError: (msg) => {
                    resetListenUi();
                    setStatus(msg);
                    scheduleRetry(startListeningCycle);
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

    let resetArmed = false;
    let resetTimer = null;

    function disarmReset() {
        resetArmed = false;
        if (resetTimer) { clearTimeout(resetTimer); resetTimer = null; }
        resetBtn.textContent = 'Начать заново';
    }

    resetBtn.addEventListener('click', () => {
        if (!nativeReady) return;
        if (!resetArmed) {
            resetArmed = true;
            resetBtn.textContent = 'Нажмите ещё раз, чтобы сбросить';
            setStatus('Точно начать заново? Текущий сеансовый ключ (если есть) будет забыт. Нажмите «Начать заново» ещё раз.');
            resetTimer = setTimeout(disarmReset, 4000);
            return;
        }
        disarmReset();
        cancelActivity();
        E2E.reset();
        setStatus('Сопряжение сброшено. Можно начинать заново.');
        resultEl.textContent = '';
        refreshBanner();
    });
});
