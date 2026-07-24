const AudioModem = (() => {
    const core = window.__TAURI__ && window.__TAURI__.core;
    const events = window.__TAURI__ && window.__TAURI__.event;

    function hexToBytes(hex) {
        const bytes = [];
        for (let i = 0; i < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
        return bytes;
    }
    function bytesToHex(bytes) {
        return bytes.map(b => b.toString(16).padStart(2, '0')).join('');
    }

    async function invokeWithStatus(command, args, onStatus) {
        if (!core) {
            const msg = 'Нативный звук доступен только в приложении.';
            onStatus && onStatus(msg);
            throw new Error(msg);
        }
        const unlisten = [];
        if (events && onStatus) {
            try {
                unlisten.push(await events.listen('modem-status', e => onStatus(e.payload)));
            } catch (e) {}
        }
        try {
            const result = await core.invoke(command, args);
            onStatus && onStatus(result);
            return result;
        } finally {
            unlisten.forEach(u => { try { u(); } catch (e) {} });
        }
    }

    function sendHexPayload(hexString, onStatus, modulation) {
        return invokeWithStatus('send_payload_arq', { hex: hexString, modulation: modulation || null }, onStatus);
    }

    function sendFileHex(name, hexString, onStatus, modulation) {
        return invokeWithStatus('send_file_arq', { name, hex: hexString, modulation: modulation || null }, onStatus);
    }

    function startListening({ onStatus, onDecoded, onError, onLevel, onStopped, onFile } = {}) {
        let finished = false;
        const unlisten = [];
        function cleanup() {
            unlisten.forEach(u => { try { u(); } catch (e) {} });
            unlisten.length = 0;
        }
        (async () => {
            if (!core || !events) {
                onError && onError('Нативный звук доступен только в приложении.');
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
                    else onStatus && onStatus('Получен файл: ' + e.payload.name);
                }));
                unlisten.push(await events.listen('modem-error', e => {
                    if (finished) return;
                    finished = true;
                    cleanup();
                    onError && onError(e.payload);
                }));
                unlisten.push(await events.listen('modem-stopped', e => {
                    if (finished) return;
                    finished = true;
                    cleanup();
                    if (onStopped) onStopped(e.payload);
                    else onStatus && onStatus(e.payload);
                }));
                await core.invoke('start_listening');
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
        playPublicKeyHex: sendHexPayload,
        playHexPayload: sendHexPayload,
        sendHexPayload,
        sendFileHex,
        startListening,
        hexToBytes,
        bytesToHex,
        setDebug() {},
    };
})();
