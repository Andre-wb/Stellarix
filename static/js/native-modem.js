const AudioModem = (() => {
    const core = window.__TAURI__ && window.__TAURI__.core;
    const events = window.__TAURI__ && window.__TAURI__.event;

    const UNAVAILABLE = 'Передача звуком работает только в приложении Stellarix. ' +
        'В обычном браузере доступа к аудиоустройствам у страницы нет — откройте настольное приложение.';

    function isAvailable() {
        return !!(core && events);
    }

    function requireNative() {
        if (!isAvailable()) throw new Error(UNAVAILABLE);
    }

    function hexToBytes(hex) {
        const bytes = [];
        for (let i = 0; i < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
        return bytes;
    }
    function bytesToHex(bytes) {
        return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    async function playHexPayload(hexString, onStatus) {
        requireNative();
        onStatus && onStatus('Передаю звуком...');
        let unlisten = null;
        try {
            if (events && onStatus) {
                unlisten = await events.listen('modem-status', e => onStatus(e.payload));
            }
            const completed = await core.invoke('play_payload', { hex: hexString });
            onStatus && onStatus(completed === false ? 'Передача отменена.' : 'Передача завершена.');
        } catch (e) {
            onStatus && onStatus('Ошибка передачи: ' + e);
        } finally {
            if (unlisten) {
                try { unlisten(); } catch (e) {}
            }
        }
    }

    async function sendFile(name, hexContent, keyHex, onStatus) {
        requireNative();
        onStatus && onStatus('Передаю файл звуком...');
        let unlisten = null;
        try {
            if (events && onStatus) {
                unlisten = await events.listen('modem-status', e => onStatus(e.payload));
            }
            const completed = await core.invoke('send_file', { name: name, hex: hexContent, key: keyHex || '' });
            onStatus && onStatus(completed === false ? 'Передача отменена.' : 'Файл передан.');
            return completed !== false;
        } catch (e) {
            onStatus && onStatus('Ошибка передачи: ' + e);
            return false;
        } finally {
            if (unlisten) {
                try { unlisten(); } catch (e) {}
            }
        }
    }

    function stopPlaying() {
        if (core) core.invoke('stop_playing').catch(() => {});
    }

    function startListening({ key, onStatus, onDecoded, onFile, onError, onLevel } = {}) {
        let finished = false;
        const unlisten = [];
        function cleanup() {
            unlisten.forEach(u => { try { u(); } catch (e) {} });
            unlisten.length = 0;
        }
        (async () => {
            if (!isAvailable()) {
                onError && onError(UNAVAILABLE);
                return;
            }
            try {
                unlisten.push(await events.listen('modem-level', e => { if (!finished) onLevel && onLevel(e.payload); }));
                unlisten.push(await events.listen('modem-status', e => { if (!finished) onStatus && onStatus(e.payload); }));
                unlisten.push(await events.listen('modem-packets', e => { if (!finished) onStatus && onStatus(`Принято пакетов: ${e.payload.have}/${e.payload.total}`); }));
                unlisten.push(await events.listen('modem-decoded', e => {
                    if (finished) return;
                    finished = true;
                    cleanup();
                    onDecoded && onDecoded(e.payload);
                }));
                unlisten.push(await events.listen('modem-file', e => {
                    if (finished) return;
                    finished = true;
                    cleanup();
                    if (onFile) onFile(e.payload);
                    else onError && onError('Принят файл, но эта страница его не принимает. Откройте чат.');
                }));
                unlisten.push(await events.listen('modem-error', e => {
                    if (finished) return;
                    finished = true;
                    cleanup();
                    onError && onError(e.payload);
                }));
                await core.invoke('start_listening', { key: key || '' });
                onStatus && onStatus('Слушаю через микрофон...');
            } catch (e) {
                if (!finished) {
                    finished = true;
                    cleanup();
                    onError && onError('Не удалось начать приём: ' + e);
                }
            }
        })();

        return {
            stop() { if (core) core.invoke('stop_listening').catch(() => {}); },
            cancel() {
                finished = true;
                cleanup();
                if (core) core.invoke('stop_listening').catch(() => {});
            },
        };
    }

    return {
        isAvailable,
        unavailableReason: UNAVAILABLE,
        playPublicKeyHex: playHexPayload,
        playHexPayload,
        sendFile,
        stopPlaying,
        startListening,
        hexToBytes,
        bytesToHex,
        setDebug() {},
    };
})();
