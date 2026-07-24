const WebAudioModem = (() => {
    const FREQ0 = 1200;
    const FREQ1 = 1800;
    const BIT_DURATION = 0.06;
    const PREAMBLE = [1,0,1,0,1,0,1,0,1,1];
    const GAP_SECONDS = 0.2;
    const SILENCE_BEFORE = 0.3;
    const SILENCE_AFTER = 0.4;
    const MAX_PAYLOAD_LEN = 96;
    const PKT_CHUNK = 4;
    const PKT_NPARITY = 2;
    const PKT_HEADER = 3;
    const PKT_DATA = PKT_HEADER + PKT_CHUNK;
    const PKT_BYTES = PKT_DATA + PKT_NPARITY;
    const PRIM = 0x11D;
    const PLAYBACK_GAIN = 0.6;

    let DEBUG = true;
    function log(...a) { if (DEBUG) console.log('[AudioModem]', ...a); }

    const GF_EXP = new Array(512).fill(0);
    const GF_LOG = new Array(256).fill(0);
    function gfMulNoLUT(x, y) {
        let r = 0;
        while (y > 0) {
            if (y & 1) r ^= x;
            y >>= 1;
            x <<= 1;
            if (x & 0x100) x ^= PRIM;
        }
        return r;
    }
    (function () {
        let x = 1;
        for (let i = 0; i < 255; i++) { GF_EXP[i] = x; GF_LOG[x] = i; x = gfMulNoLUT(x, 2); }
        for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
    })();
    function gfMul(x, y) { if (x === 0 || y === 0) return 0; return GF_EXP[GF_LOG[x] + GF_LOG[y]]; }
    function gfPow(x, p) { return GF_EXP[((GF_LOG[x] * p) % 255 + 255) % 255]; }
    function gfPolyMul(p, q) {
        const r = new Array(p.length + q.length - 1).fill(0);
        for (let j = 0; j < q.length; j++) for (let i = 0; i < p.length; i++) r[i + j] ^= gfMul(p[i], q[j]);
        return r;
    }
    function rsGeneratorPoly(nsym) {
        let g = [1];
        for (let i = 0; i < nsym; i++) g = gfPolyMul(g, [1, gfPow(2, i)]);
        return g;
    }
    function rsEncodeMsg(msgIn, nsym) {
        const gen = rsGeneratorPoly(nsym);
        const out = msgIn.concat(new Array(gen.length - 1).fill(0));
        for (let i = 0; i < msgIn.length; i++) {
            const coef = out[i];
            if (coef !== 0) for (let j = 1; j < gen.length; j++) out[i + j] ^= gfMul(gen[j], coef);
        }
        for (let i = 0; i < msgIn.length; i++) out[i] = msgIn[i];
        return out;
    }

    function crc32(bytes) {
        let crc = 0xFFFFFFFF;
        for (const byte of bytes) {
            crc ^= byte;
            for (let i = 0; i < 8; i++) crc = (crc & 1) ? ((crc >>> 1) ^ 0xEDB88320) : (crc >>> 1);
        }
        return (crc ^ 0xFFFFFFFF) >>> 0;
    }

    function byteToBits(byte) {
        const b = [];
        for (let i = 7; i >= 0; i--) b.push((byte >> i) & 1);
        return b;
    }
    function hexToBytes(hex) {
        const bytes = [];
        for (let i = 0; i < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
        return bytes;
    }
    function bytesToHex(bytes) {
        return bytes.map(b => b.toString(16).padStart(2, '0')).join('');
    }

    function buildPackets(payloadBytes) {
        const len = payloadBytes.length;
        const crc = crc32([len, ...payloadBytes]);
        const withCrc = [len, ...payloadBytes, (crc >>> 24) & 0xFF, (crc >>> 16) & 0xFF, (crc >>> 8) & 0xFF, crc & 0xFF];
        const total = Math.ceil(withCrc.length / PKT_CHUNK);
        const packets = [];
        for (let seq = 0; seq < total; seq++) {
            const chunk = [];
            for (let i = 0; i < PKT_CHUNK; i++) {
                const idx = seq * PKT_CHUNK + i;
                chunk.push(idx < withCrc.length ? withCrc[idx] : 0);
            }
            const data = [seq, total, withCrc.length, ...chunk];
            packets.push(rsEncodeMsg(data, PKT_NPARITY));
        }
        return packets;
    }

    function packetToBits(body) {
        const bits = [...PREAMBLE];
        for (const byte of body) bits.push(...byteToBits(byte));
        return bits;
    }

    function totalSeconds(payloadBytes) {
        const packets = buildPackets(payloadBytes);
        const perPacket = (PREAMBLE.length + PKT_BYTES * 8) * BIT_DURATION + GAP_SECONDS;
        return SILENCE_BEFORE + packets.length * perPacket + SILENCE_AFTER;
    }
    function maxTotalSeconds() {
        const dummy = new Array(MAX_PAYLOAD_LEN).fill(0);
        return totalSeconds(dummy);
    }

    function playPackets(audioCtx, packets) {
        return new Promise((resolve) => {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = 'sine';
            osc.connect(gain);
            gain.connect(audioCtx.destination);

            const rampTime = 0.01;
            let t = audioCtx.currentTime + SILENCE_BEFORE;
            gain.gain.setValueAtTime(0, audioCtx.currentTime);

            for (const body of packets) {
                const bits = packetToBits(body);
                gain.gain.setValueAtTime(0, t);
                gain.gain.linearRampToValueAtTime(PLAYBACK_GAIN, t + rampTime);
                for (let i = 0; i < bits.length; i++) {
                    osc.frequency.setValueAtTime(bits[i] ? FREQ1 : FREQ0, t + i * BIT_DURATION);
                }
                const packetEnd = t + bits.length * BIT_DURATION;
                gain.gain.setValueAtTime(PLAYBACK_GAIN, packetEnd - rampTime);
                gain.gain.linearRampToValueAtTime(0, packetEnd);
                t = packetEnd + GAP_SECONDS;
            }

            const endTime = t + SILENCE_AFTER;
            osc.start(audioCtx.currentTime);
            osc.stop(endTime);
            osc.onended = () => resolve();
        });
    }

    async function playHexPayload(hexString, onStatus) {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        await audioCtx.resume();
        const bytes = hexToBytes(hexString);
        const packets = buildPackets(bytes);
        const seconds = totalSeconds(bytes).toFixed(1);
        log(`playHexPayload: ${bytes.length} байт, ${packets.length} пакетов, ${seconds}с`);
        onStatus && onStatus(`Передаю ${bytes.length} байт (${packets.length} пакетов, ~${seconds} сек)`);
        await playPackets(audioCtx, packets);
        onStatus && onStatus('Передача завершена.');
        await audioCtx.close();
    }

    function computeRms(samples) {
        let sum = 0;
        for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
        return Math.sqrt(sum / samples.length);
    }

    function startListening({ onStatus, onDecoded, onError, onLevel, timeoutMs } = {}) {
        const effectiveTimeoutMs = timeoutMs || Math.ceil((maxTotalSeconds() * 2 + 5) * 1000);
        let audioCtx, source, processor, stream, silentGain, worker;
        let timeoutHandle = null;
        let smoothedRms = 0;
        let finished = false;
        let analyzing = false;

        log(`startListening: таймаут=${effectiveTimeoutMs}мс`);

        (async () => {
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
                });

                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                await audioCtx.resume();
                source = audioCtx.createMediaStreamSource(stream);

                worker = new Worker('/static/js/audio-decoder-worker.js');
                worker.onmessage = (e) => {
                    const msg = e.data;
                    if (msg.type === 'decoded') {
                        finishSuccess(msg.payload);
                    } else if (msg.type === 'notfound') {
                        finishFailure(msg.hint);
                    } else if (msg.type === 'progress') {
                        onStatus && onStatus(`Анализирую запись... ${msg.percent}%`);
                    } else if (msg.type === 'packets') {
                        onStatus && onStatus(`Принято пакетов: ${msg.have}/${msg.total}`);
                    }
                };
                worker.postMessage({ type: 'init', sampleRate: audioCtx.sampleRate });

                const bufferSize = 4096;
                processor = audioCtx.createScriptProcessor(bufferSize, 1, 1);

                onStatus && onStatus('Слушаю через микрофон...');

                processor.onaudioprocess = (e) => {
                    if (finished || analyzing) return;
                    const input = e.inputBuffer.getChannelData(0);
                    const rms = computeRms(input);
                    smoothedRms = smoothedRms * 0.7 + rms * 0.3;
                    onLevel && onLevel(smoothedRms);

                    const chunk = new Float32Array(input);
                    worker.postMessage({ type: 'feed', samples: chunk }, [chunk.buffer]);
                };

                source.connect(processor);
                silentGain = audioCtx.createGain();
                silentGain.gain.value = 0;
                processor.connect(silentGain);
                silentGain.connect(audioCtx.destination);

                timeoutHandle = setTimeout(() => {
                    if (!finished && !analyzing) stopAndAnalyze();
                }, effectiveTimeoutMs);
            } catch (err) {
                onError && onError('Не удалось получить доступ к микрофону: ' + err.message);
            }
        })();

        function finishSuccess(payload) {
            if (finished) return;
            finished = true;
            clearTimeout(timeoutHandle);
            fullCleanup();
            onDecoded && onDecoded(bytesToHex(payload));
        }

        function finishFailure(hint) {
            if (finished) return;
            finished = true;
            clearTimeout(timeoutHandle);
            fullCleanup();
            onError && onError('Не удалось распознать сигнал. ' + (hint || 'Проверьте уровень микрофона и расстояние между устройствами.'));
        }

        function stopAndAnalyze() {
            if (finished || analyzing) return;
            analyzing = true;
            clearTimeout(timeoutHandle);
            onStatus && onStatus('Останавливаю запись, анализирую...');
            stopMicOnly();
            worker && worker.postMessage({ type: 'stop-and-analyze' });
        }

        function stopMicOnly() {
            try { processor && processor.disconnect(); } catch (e) {}
            try { silentGain && silentGain.disconnect(); } catch (e) {}
            try { source && source.disconnect(); } catch (e) {}
            try { stream && stream.getTracks().forEach(t => t.stop()); } catch (e) {}
            try { audioCtx && audioCtx.close(); } catch (e) {}
        }

        function fullCleanup() {
            stopMicOnly();
            try { worker && worker.terminate(); } catch (e) {}
        }

        return {
            stop: stopAndAnalyze,
            cancel: () => { finished = true; fullCleanup(); },
        };
    }

    return {
        playPublicKeyHex: playHexPayload,
        playHexPayload,
        startListening,
        hexToBytes,
        bytesToHex,
        setDebug(v) { DEBUG = !!v; },
    };
})();
