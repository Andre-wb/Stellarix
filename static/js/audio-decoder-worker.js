const FREQ0 = 1200;
const FREQ1 = 1800;
const BIT_DURATION = 0.06;
const PREAMBLE = [1,0,1,0,1,0,1,0,1,1];
const GAP_SECONDS = 0.2;
const MAX_PAYLOAD_LEN = 96;
const PKT_CHUNK = 4;
const PKT_NPARITY = 2;
const PKT_HEADER = 3;
const PKT_DATA = PKT_HEADER + PKT_CHUNK;
const PKT_BYTES = PKT_DATA + PKT_NPARITY;
const PRIM = 0x11D;

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
function gfDiv(x, y) { if (x === 0) return 0; return GF_EXP[(GF_LOG[x] + 255 - GF_LOG[y]) % 255]; }
function gfPow(x, p) { return GF_EXP[((GF_LOG[x] * p) % 255 + 255) % 255]; }
function gfInverse(x) { return GF_EXP[255 - GF_LOG[x]]; }
function gfPolyScale(p, s) { return p.map(c => gfMul(c, s)); }
function gfPolyAdd(p, q) {
    const r = new Array(Math.max(p.length, q.length)).fill(0);
    for (let i = 0; i < p.length; i++) r[i + r.length - p.length] = p[i];
    for (let i = 0; i < q.length; i++) r[i + r.length - q.length] ^= q[i];
    return r;
}
function gfPolyMul(p, q) {
    const r = new Array(p.length + q.length - 1).fill(0);
    for (let j = 0; j < q.length; j++) for (let i = 0; i < p.length; i++) r[i + j] ^= gfMul(p[i], q[j]);
    return r;
}
function gfPolyEval(p, x) { let y = p[0]; for (let i = 1; i < p.length; i++) y = gfMul(y, x) ^ p[i]; return y; }
function gfPolyMod(dividend, divisor) {
    const out = dividend.slice();
    for (let i = 0; i < dividend.length - (divisor.length - 1); i++) {
        const coef = out[i];
        if (coef !== 0) for (let j = 1; j < divisor.length; j++) if (divisor[j] !== 0) out[i + j] ^= gfMul(divisor[j], coef);
    }
    return out.slice(dividend.length - (divisor.length - 1));
}
function rsCalcSyndromes(msg, nsym) {
    const s = new Array(nsym + 1).fill(0);
    for (let i = 0; i < nsym; i++) s[i + 1] = gfPolyEval(msg, gfPow(2, i));
    return s;
}
function rsFindErrataLocator(ePos) {
    let e = [1];
    for (const i of ePos) e = gfPolyMul(e, gfPolyAdd([1], [gfPow(2, i), 0]));
    return e;
}
function rsFindErrorEvaluator(synd, errLoc, nsym) {
    const mul = gfPolyMul(synd, errLoc);
    const divisor = new Array(nsym + 2).fill(0);
    divisor[0] = 1;
    return gfPolyMod(mul, divisor);
}
function rsCorrectErrata(msgIn, synd, errPos) {
    const coefPos = errPos.map(p => msgIn.length - 1 - p);
    const errLoc = rsFindErrataLocator(coefPos);
    const errEval = rsFindErrorEvaluator(synd.slice().reverse(), errLoc, errLoc.length - 1).reverse();
    const X = coefPos.map(cp => gfPow(2, -(255 - cp)));
    const E = new Array(msgIn.length).fill(0);
    for (let i = 0; i < X.length; i++) {
        const XiInv = gfInverse(X[i]);
        let prime = 1;
        for (let j = 0; j < X.length; j++) if (j !== i) prime = gfMul(prime, 1 ^ gfMul(XiInv, X[j]));
        if (prime === 0) throw new Error('prime zero');
        let y = gfPolyEval(errEval.slice().reverse(), XiInv);
        y = gfMul(gfPow(X[i], 1), y);
        E[errPos[i]] = gfDiv(y, prime);
    }
    return gfPolyAdd(msgIn, E);
}
function rsFindErrorLocator(synd, nsym, eraseCount) {
    let errLoc = [1], oldLoc = [1];
    eraseCount = eraseCount || 0;
    const syndShift = synd.length > nsym ? synd.length - nsym : 0;
    for (let i = 0; i < nsym - eraseCount; i++) {
        const K = i + syndShift;
        let delta = synd[K];
        for (let j = 1; j < errLoc.length; j++) delta ^= gfMul(errLoc[errLoc.length - 1 - j], synd[K - j]);
        oldLoc = oldLoc.concat([0]);
        if (delta !== 0) {
            if (oldLoc.length > errLoc.length) {
                const newLoc = gfPolyScale(oldLoc, delta);
                oldLoc = gfPolyScale(errLoc, gfInverse(delta));
                errLoc = newLoc;
            }
            errLoc = gfPolyAdd(errLoc, gfPolyScale(oldLoc, delta));
        }
    }
    while (errLoc.length && errLoc[0] === 0) errLoc.shift();
    if ((errLoc.length - 1 - eraseCount) * 2 + eraseCount > nsym) throw new Error('too many errors');
    return errLoc;
}
function rsFindErrors(errLoc, nmess) {
    const errs = errLoc.length - 1;
    const pos = [];
    for (let i = 0; i < nmess; i++) if (gfPolyEval(errLoc, gfPow(2, i)) === 0) pos.push(nmess - 1 - i);
    if (pos.length !== errs) throw new Error('find errors');
    return pos;
}
function rsForneySyndromes(synd, pos, nmess) {
    const rev = pos.map(p => nmess - 1 - p);
    const f = synd.slice(1);
    for (let i = 0; i < rev.length; i++) {
        const x = gfPow(2, rev[i]);
        for (let j = 0; j < f.length - 1; j++) f[j] = gfMul(f[j], x) ^ f[j + 1];
    }
    return f;
}
function rsCorrectMsg(msgIn, nsym, erasePos) {
    const msgOut = msgIn.slice();
    erasePos = erasePos ? erasePos.slice() : [];
    for (const e of erasePos) msgOut[e] = 0;
    if (erasePos.length > nsym) throw new Error('too many erasures');
    const synd = rsCalcSyndromes(msgOut, nsym);
    if (Math.max(...synd) === 0) return msgOut;
    const fsynd = rsForneySyndromes(synd, erasePos, msgOut.length);
    const errLoc = rsFindErrorLocator(fsynd, nsym, erasePos.length);
    const errPos = rsFindErrors(errLoc.slice().reverse(), msgOut.length);
    const corrected = rsCorrectErrata(msgOut, synd, erasePos.concat(errPos));
    if (Math.max(...rsCalcSyndromes(corrected, nsym)) > 0) throw new Error('could not correct');
    return corrected;
}

function crc32(bytes) {
    let crc = 0xFFFFFFFF;
    for (const byte of bytes) {
        crc ^= byte;
        for (let i = 0; i < 8; i++) crc = (crc & 1) ? ((crc >>> 1) ^ 0xEDB88320) : (crc >>> 1);
    }
    return (crc ^ 0xFFFFFFFF) >>> 0;
}

function bitsToByte(bits) { let v = 0; for (let i = 0; i < 8; i++) v = (v << 1) | (bits[i] & 1); return v; }

function goertzelMag(samples, offset, length, sampleRate, freq) {
    const k = Math.round((length * freq) / sampleRate);
    const w = (2 * Math.PI * k) / length;
    const coeff = 2 * Math.cos(w);
    let q1 = 0, q2 = 0, q0;
    for (let i = 0; i < length; i++) { q0 = coeff * q1 - q2 + samples[offset + i]; q2 = q1; q1 = q0; }
    return Math.sqrt(q1 * q1 + q2 * q2 - q1 * q2 * coeff);
}
function bitAt(samples, offset, bitSamples, sampleRate) {
    const m0 = goertzelMag(samples, offset, bitSamples, sampleRate, FREQ0);
    const m1 = goertzelMag(samples, offset, bitSamples, sampleRate, FREQ1);
    const energy = m0 + m1;
    const confidence = energy > 1e-9 ? Math.abs(m1 - m0) / energy : 0;
    return { bit: m1 > m0 ? 1 : 0, confidence, energy };
}
function scorePreambleAt(samples, offset, bitSamples, sampleRate) {
    let score = 0, minEnergy = Infinity;
    for (let i = 0; i < PREAMBLE.length; i++) {
        const start = offset + i * bitSamples;
        if (start + bitSamples > samples.length) return { score: -Infinity, minEnergy: 0 };
        const { bit, confidence, energy } = bitAt(samples, start, bitSamples, sampleRate);
        minEnergy = Math.min(minEnergy, energy);
        score += (bit === PREAMBLE[i]) ? confidence : -confidence * 1.5;
    }
    return { score, minEnergy };
}
function decodePacketAt(samples, preambleStart, bitSamples, sampleRate) {
    const preambleSamples = PREAMBLE.length * bitSamples;
    const cursor = preambleStart + preambleSamples;
    const need = PKT_BYTES * 8 * bitSamples;
    if (cursor + need > samples.length) return null;
    const body = [];
    for (let b = 0; b < PKT_BYTES; b++) {
        const bits = [];
        for (let i = 0; i < 8; i++) bits.push(bitAt(samples, cursor + (b * 8 + i) * bitSamples, bitSamples, sampleRate).bit);
        body.push(bitsToByte(bits));
    }
    let data;
    try { data = rsCorrectMsg(body, PKT_NPARITY, null); } catch (e) { return null; }
    const seq = data[0], total = data[1], withCrcLen = data[2];
    if (total < 1 || total > 64) return null;
    if (seq >= total) return null;
    if (withCrcLen < 5 || withCrcLen > MAX_PAYLOAD_LEN + 5) return null;
    return { seq, total, withCrcLen, chunk: data.slice(PKT_HEADER, PKT_HEADER + PKT_CHUNK) };
}
function refinePreamble(samples, coarse, bitSamples, sampleRate, radius, step) {
    let best = -Infinity, bestOff = coarse;
    for (let d = -radius; d <= radius; d += step) {
        const off = coarse + d;
        if (off < 0) continue;
        const { score } = scorePreambleAt(samples, off, bitSamples, sampleRate);
        if (score > best) { best = score; bestOff = off; }
    }
    return bestOff;
}
function decodeRecording(samples, sampleRate) {
    const bitSamples = Math.round(BIT_DURATION * sampleRate);
    const searchStep = Math.max(1, Math.round(bitSamples / 6));
    const preambleSamples = PREAMBLE.length * bitSamples;
    const maxStart = samples.length - preambleSamples;
    if (maxStart <= 0) return { payload: null, have: 0, total: null };
    const lockThreshold = PREAMBLE.length * 0.35;

    const cand = [];
    for (let offset = 0; offset <= maxStart; offset += searchStep) {
        const { score } = scorePreambleAt(samples, offset, bitSamples, sampleRate);
        if (score >= lockThreshold) cand.push({ offset, score });
    }
    cand.sort((a, b) => b.score - a.score);

    const picked = [];
    const minSep = Math.round(preambleSamples * 0.75);
    for (const c of cand) {
        let near = false;
        for (const p of picked) if (Math.abs(c.offset - p) < minSep) { near = true; break; }
        if (!near) picked.push(c.offset);
    }

    const chunks = new Map();
    let total = null, withCrcLen = null;
    const refineRadius = searchStep;
    const refineStep = Math.max(1, Math.round(bitSamples / 40));

    for (const coarse of picked) {
        const refined = refinePreamble(samples, coarse, bitSamples, sampleRate, refineRadius, refineStep);
        const pkt = decodePacketAt(samples, refined, bitSamples, sampleRate);
        if (!pkt) continue;
        if (total === null) { total = pkt.total; withCrcLen = pkt.withCrcLen; }
        if (pkt.total !== total || pkt.withCrcLen !== withCrcLen) continue;
        if (!chunks.has(pkt.seq)) chunks.set(pkt.seq, pkt.chunk);
        if (chunks.size === total) break;
    }

    if (total === null) return { payload: null, have: 0, total: null };
    if (chunks.size < total) return { payload: null, have: chunks.size, total };

    const withCrc = [];
    for (let seq = 0; seq < total; seq++) {
        const chunk = chunks.get(seq);
        if (!chunk) return { payload: null, have: chunks.size, total };
        for (const b of chunk) withCrc.push(b);
    }
    const trimmed = withCrc.slice(0, withCrcLen);
    const len = trimmed[0];
    if (len < 0 || len > MAX_PAYLOAD_LEN || len + 5 !== withCrcLen) return { payload: null, have: chunks.size, total };
    const payload = trimmed.slice(1, 1 + len);
    const expected = crc32([len, ...payload]);
    const received = ((trimmed[1 + len] << 24) | (trimmed[1 + len + 1] << 16) | (trimmed[1 + len + 2] << 8) | trimmed[1 + len + 3]) >>> 0;
    if (expected !== received) return { payload: null, have: chunks.size, total };
    return { payload, have: total, total };
}

let sampleRate = 44100;
let capturedBuf = new Float32Array(0);
let capturedLen = 0;
let lastAttemptLen = 0;
let attemptInterval = 44100 * 4;

function ensureCapacity(extra) {
    if (capturedLen + extra > capturedBuf.length) {
        const grown = new Float32Array(Math.max(capturedBuf.length * 2, capturedLen + extra));
        grown.set(capturedBuf.subarray(0, capturedLen));
        capturedBuf = grown;
    }
}

self.onmessage = (e) => {
    const msg = e.data;

    if (msg.type === 'init') {
        sampleRate = msg.sampleRate;
        capturedBuf = new Float32Array(Math.ceil(sampleRate * 120));
        capturedLen = 0;
        lastAttemptLen = 0;
        attemptInterval = Math.round(sampleRate * 4);

    } else if (msg.type === 'feed') {
        const chunk = msg.samples;
        ensureCapacity(chunk.length);
        capturedBuf.set(chunk, capturedLen);
        capturedLen += chunk.length;

        if (capturedLen - lastAttemptLen >= attemptInterval) {
            lastAttemptLen = capturedLen;
            const view = capturedBuf.subarray(0, capturedLen);
            const result = decodeRecording(view, sampleRate);
            if (result.payload) {
                self.postMessage({ type: 'decoded', payload: result.payload });
            } else if (result.total) {
                self.postMessage({ type: 'packets', have: result.have, total: result.total });
            }
        }

    } else if (msg.type === 'stop-and-analyze') {
        const view = capturedBuf.subarray(0, capturedLen);
        self.postMessage({ type: 'progress', percent: 50 });
        const result = decodeRecording(view, sampleRate);
        if (result.payload) {
            self.postMessage({ type: 'decoded', payload: result.payload });
        } else {
            let hint;
            if (result.total === null) {
                hint = 'Сигнал почти не слышен. Сблизьте устройства и увеличьте громкость.';
            } else {
                hint = `Принято ${result.have} из ${result.total} пакетов. Повторите передачу ближе друг к другу или увеличьте громкость.`;
            }
            self.postMessage({ type: 'notfound', hint });
        }
    }
};
