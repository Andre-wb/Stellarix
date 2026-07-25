document.addEventListener('DOMContentLoaded', () => {
    const shareBtn = document.getElementById('share-key-btn');
    const receiveBtn = document.getElementById('receive-key-btn');
    const stopBtn = document.getElementById('stop-key-btn');
    const resetBtn = document.getElementById('reset-key-btn');
    const statusEl = document.getElementById('pairing-status');
    const resultEl = document.getElementById('pairing-result');
    const levelEl = document.getElementById('mic-level');
    const bannerEl = document.getElementById('pairing-banner');
    const peerBox = document.getElementById('pairing-peer');
    const peerAvatarEl = document.getElementById('pairing-peer-avatar');
    const peerLabelEl = document.getElementById('pairing-peer-label');
    const nativeReady = AudioModem.isAvailable();
    const IDLE_LEVEL = 'Уровень микрофона: [--------------------]';
    let activeListener = null;
    let retryCount = 0;
    let retryTimer = null;
    let sharing = false;
    let shareGen = 0;
    let keypairPromise = null;
    const MAX_RETRIES = 3;

    function setStatus(text) {
        statusEl.textContent = text;
    }

    const hasAvatar = typeof Avatar !== 'undefined';

    function ownName() {
        const el = document.querySelector('.chat-user');
        return el ? (el.textContent || '').trim() : '';
    }

    function showPeerAvatar(dataUrl) {
        if (!peerBox || !hasAvatar) return;
        Avatar.render(peerAvatarEl, dataUrl, Avatar.peerLetter());
        peerLabelEl.textContent = dataUrl
            ? 'Аватар собеседника получен — он будет слева в чате.'
            : '';
        peerBox.classList.add('show');
    }

    function hidePeerAvatar() {
        if (peerBox) peerBox.classList.remove('show');
    }

    function applyPeerFromProfile(profileHex) {
        if (!hasAvatar) return;
        const profile = Avatar.parseProfileHex(profileHex);
        Avatar.setPeerName(profile.name);
        Avatar.setPeer(profile.avatar);
        showPeerAvatar(profile.avatar);
    }

    if (hasAvatar && E2E.isPaired() && Avatar.getPeer()) {
        showPeerAvatar(Avatar.getPeer());
    }

    function setLevel(rms) {
        if (!levelEl) return;
        const bars = Math.max(0, Math.min(20, Math.round(rms * 250)));
        levelEl.textContent = 'Уровень микрофона: [' + '#'.repeat(bars) + '-'.repeat(20 - bars) + ']';
    }

    function wasDelivered(report) {
        return /^Доставлено/.test(report || '');
    }

    function wasStopped(report) {
        return /остановлена/.test(report || '');
    }

    function legacyPaired() {
        return E2E.isPaired() && !E2E.hasKeypair();
    }

    function enableShare() {
        shareBtn.disabled = !cryptoOk || legacyPaired();
    }

    function keypairReady() {
        if (!keypairPromise) {
            keypairPromise = E2E.ensureKeypair().catch(err => {
                keypairPromise = null;
                throw err;
            });
        }
        return keypairPromise;
    }

    function resetListenUi() {
        activeListener = null;
        receiveBtn.disabled = false;
        enableShare();
        stopBtn.style.display = 'none';
    }

    function scheduleRetry(startFn) {
        if (!nativeReady || retryCount >= MAX_RETRIES) return;
        retryCount++;
        setStatus(`Повторная попытка (${retryCount}/${MAX_RETRIES})...`);
        retryTimer = setTimeout(() => { retryTimer = null; startFn(); }, 2000);
    }

    function cancelListening() {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        if (activeListener) activeListener.cancel();
        resetListenUi();
        retryCount = 0;
    }

    function cancelSharing() {
        if (!sharing) return;
        shareGen++;
        sharing = false;
        AudioModem.stopPlaying();
    }

    function cancelActivity() {
        shareGen++;
        sharing = false;
        cancelListening();
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
        if (!cryptoOk) {
            bannerEl.style.display = 'none';
            return;
        }
        bannerEl.style.display = 'block';
        if (legacyPaired()) {
            bannerEl.style.background = 'rgba(230, 180, 30, 0.15)';
            bannerEl.innerHTML =
                StxIcons.warn + ' Сеансовый ключ создан прежней версией приложения, и ваш собственный ключ для повторной ' +
                'передачи не сохранён — поделиться им уже нельзя. Отпечаток: <strong>' + E2E.getFingerprint() + '</strong>. ' +
                'Если собеседник ещё не принял ваш ключ, нажмите «Начать заново» и выполните обмен с обеих сторон.';
        } else if (E2E.isPaired()) {
            bannerEl.style.background = 'rgba(40, 180, 99, 0.15)';
            bannerEl.innerHTML =
                StxIcons.ok + ' Ваша сторона сопряжена. Отпечаток ключа: <strong>' + E2E.getFingerprint() + '</strong>. ' +
                'Сверьте его вслух с собеседником — отпечатки должны совпасть. Если собеседник ещё не принимал ' +
                'ваш ключ, нажмите «Поделиться ключом»: без этого он не сможет прочитать ваши сообщения. ' +
                'Когда отпечатки совпали — переходите в <a href="/chat">чат</a>.';
        } else {
            bannerEl.style.background = 'rgba(90, 140, 230, 0.15)';
            bannerEl.innerHTML =
                'Ваш ключ готов. <strong>Шаг 1:</strong> один нажимает «Поделиться ключом», второй в это же ' +
                'время — «Получить ключ». <strong>Шаг 2:</strong> поменяйтесь ролями и повторите. ' +
                'Обмен нужен в обе стороны — после одного шага чат ещё не работает.';
        }
    }

    const cryptoOk = E2E.isSupported();
    if (!cryptoOk) {
        setStatus('Встроенный движок приложения не поддерживает нужную криптографию (WebCrypto). Обновите систему или компонент WebView — без него сопряжение невозможно.');
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
    }

    refreshBanner();
    if (cryptoOk && nativeReady && !legacyPaired()) {
        keypairReady().catch(err => setStatus('Не удалось создать ключ: ' + err.message));
    }

    shareBtn.addEventListener('click', async () => {
        if (sharing || !nativeReady) return;
        if (legacyPaired()) {
            setStatus('Ваш ключ не сохранён с прошлой версии — нажмите «Начать заново» и выполните обмен заново.');
            return;
        }
        cancelListening();
        const gen = ++shareGen;
        sharing = true;
        shareBtn.disabled = true;
        receiveBtn.disabled = true;
        resultEl.textContent = '';
        const liveStatus = s => { if (gen === shareGen) setStatus(s); };
        try {
            setStatus('Готовлю ключ...');
            const publicHex = await keypairReady();
            if (gen !== shareGen) return;
            const profileHex = hasAvatar ? Avatar.profileHex(ownName()) : '';
            setStatus(hasAvatar && Avatar.getOwn() ? 'Передаю ключ и аватар...' : 'Передаю ключ...');
            const report = await AudioModem.playPublicKeyHex(publicHex + profileHex, liveStatus);
            if (gen !== shareGen) return;
            if (wasDelivered(report)) {
                setStatus(E2E.isPaired()
                    ? 'Ключ доставлен — собеседник подтвердил получение. Сопряжение завершено с обеих сторон.'
                    : 'Ключ доставлен — собеседник подтвердил получение. Теперь поменяйтесь ролями: нажмите «Получить ключ», а собеседник — «Поделиться ключом».');
            } else if (report && !wasStopped(report)) {
                setStatus(report + ' Собеседник должен нажать «Получить ключ» до того, как вы начнёте передачу — дождитесь у него надписи «Слушаю через микрофон...» и нажмите «Поделиться ключом» ещё раз.');
            }
            refreshBanner();
        } catch (err) {
            if (gen === shareGen) setStatus('Ошибка: ' + err.message);
        } finally {
            if (gen === shareGen) {
                sharing = false;
                enableShare();
                receiveBtn.disabled = false;
            }
        }
    });

    receiveBtn.addEventListener('click', () => {
        if (activeListener || !nativeReady) return;
        cancelSharing();
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        resultEl.textContent = '';
        if (levelEl) levelEl.textContent = IDLE_LEVEL;
        retryCount = 0;

        function startListeningCycle() {
            receiveBtn.disabled = true;
            enableShare();
            stopBtn.style.display = 'inline-block';
            activeListener = AudioModem.startListening({
                onStatus: setStatus,
                onLevel: setLevel,
                onDecoded: async (hex) => {
                    const peerHex = hex.slice(0, 64);
                    const profileHex = hex.slice(64);
                    const own = E2E.getPublicHex();
                    if (own && peerHex.toLowerCase() === own.toLowerCase()) {
                        activeListener = null;
                        setStatus('Пойман собственный ключ (эхо своего динамика) — продолжаю слушать собеседника...');
                        startListeningCycle();
                        return;
                    }
                    resetListenUi();
                    if (E2E.isPaired()) {
                        if (E2E.getPeerHex() === peerHex.toLowerCase()) {
                            if (profileHex) applyPeerFromProfile(profileHex);
                            setStatus('Это тот же ключ собеседника — сопряжение уже выполнено, отпечаток прежний: ' + E2E.getFingerprint());
                        } else {
                            setStatus('Принят ключ другого устройства. Текущее сопряжение сохранено — чтобы связаться с новым собеседником, нажмите «Начать заново».');
                        }
                        refreshBanner();
                        return;
                    }
                    setStatus('Ключ получен, вычисляю общий сеансовый ключ...');
                    try {
                        await keypairReady();
                        const fingerprint = await E2E.completePairing(peerHex);
                        applyPeerFromProfile(profileHex);
                        setStatus('Готово! Теперь нажмите «Поделиться ключом», чтобы собеседник тоже завершил сопряжение.');
                        resultEl.textContent =
                            'Сеансовый ключ создан в браузере. Сверьте отпечаток с собеседником вслух: ' + fingerprint;
                    } catch (err) {
                        setStatus('Ошибка: ' + err.message + ' Повторный приём это не исправит — нажмите «Начать заново» и выполните обмен снова.');
                    }
                    refreshBanner();
                },
                onError: (msg) => {
                    resetListenUi();
                    setStatus(msg);
                    scheduleRetry(startListeningCycle);
                },
                onStopped: (msg) => {
                    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
                    retryCount = 0;
                    resetListenUi();
                    setStatus(msg);
                }
            });
        }

        startListeningCycle();
    });

    stopBtn.addEventListener('click', () => {
        if (!activeListener) return;
        setStatus('Останавливаю приём...');
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
        if (hasAvatar) { Avatar.clearPeer(); Avatar.clearPeerName(); }
        hidePeerAvatar();
        keypairPromise = null;
        if (levelEl) levelEl.textContent = IDLE_LEVEL;
        keypairReady()
            .then(() => {
                setStatus('Сопряжение сброшено, новый ключ готов. Можно начинать заново.');
                refreshBanner();
            })
            .catch(err => setStatus('Не удалось создать ключ: ' + err.message));
        resultEl.textContent = '';
        refreshBanner();
    });
});
