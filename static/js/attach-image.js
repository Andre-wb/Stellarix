const AttachImage = (() => {
    const COMPRESS_PRESETS = [
        { label: 'Максимум', hint: 'лимит 64 КиБ', bytes: 64 * 1024 },
        { label: 'Компактно', hint: '≈24 КиБ', bytes: 24 * 1024 },
        { label: 'Крошечно', hint: '≈12 КиБ', bytes: 12 * 1024 },
    ];
    const FALLBACK_BPS = 350;

    function fmtSize(bytes) {
        if (bytes < 1024) return bytes + ' Б';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КиБ';
        return (bytes / (1024 * 1024)).toFixed(1) + ' МиБ';
    }

    function fmtTime(seconds) {
        const s = Math.max(1, Math.round(seconds));
        if (s < 60) return '≈' + s + ' с';
        const m = Math.floor(s / 60);
        const rest = s % 60;
        return '≈' + m + ' мин' + (rest ? ' ' + rest + ' с' : '');
    }

    function fmtType(type) {
        if (type === 'image/webp') return 'WebP';
        if (type === 'image/jpeg') return 'JPEG';
        if (!type) return 'оригинал';
        return type.replace('image/', '').toUpperCase();
    }

    function estimateBps() {
        try {
            if (typeof StxStats === 'undefined') return FALLBACK_BPS;
            const tx = StxStats.all().filter((x) => x.kind === 'tx' && x.ok && x.bytes > 0 && x.ms > 0);
            if (!tx.length) return FALLBACK_BPS;
            const rates = tx.map((x) => x.bytes / (x.ms / 1000)).sort((a, b) => a - b);
            return rates[Math.floor(rates.length / 2)] || FALLBACK_BPS;
        } catch (e) {
            return FALLBACK_BPS;
        }
    }

    function stemOf(name) {
        const dot = (name || '').lastIndexOf('.');
        return dot > 0 ? name.slice(0, dot) : (name || 'image');
    }

    function imageDims(file) {
        return new Promise((resolve, reject) => {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => { const d = { w: img.naturalWidth, h: img.naturalHeight }; URL.revokeObjectURL(url); resolve(d); };
            img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('не удалось прочитать изображение')); };
            img.src = url;
        });
    }

    function el(tag, cls, text) {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    }

    function open(file, opts) {
        opts = opts || {};
        const maxBytes = opts.maxBytes || 64 * 1024;
        const bps = estimateBps();
        const originalAllowed = typeof FilePolicy === 'undefined' || FilePolicy.isAllowed(file.name);
        const canPassthrough = file.size <= maxBytes && originalAllowed;

        const presetList = [];
        if (canPassthrough) presetList.push({ label: 'Оригинал', hint: 'без потерь', original: true });
        COMPRESS_PRESETS.forEach((p) => presetList.push(p));

        return new Promise((resolve) => {
            let current = null;
            let previewUrl = null;
            let activePreset = canPassthrough ? 0 : 1;
            let busy = false;
            let settled = false;

            const overlay = el('div', 'imgc-overlay');
            const card = el('div', 'imgc-card');
            overlay.appendChild(card);

            const head = el('div', 'imgc-head');
            head.appendChild(el('div', 'imgc-title', 'Сжатие для передачи звуком'));
            head.appendChild(el('div', 'imgc-sub', file.name));
            card.appendChild(head);

            const body = el('div', 'imgc-body');
            const thumbWrap = el('div', 'imgc-thumb');
            const thumb = el('img', 'imgc-img');
            thumb.alt = 'Предпросмотр';
            thumbWrap.appendChild(thumb);
            const badge = el('div', 'imgc-badge');
            thumbWrap.appendChild(badge);
            body.appendChild(thumbWrap);

            const info = el('div', 'imgc-info');
            const rowOrig = el('div', 'imgc-row');
            const rowRes = el('div', 'imgc-row imgc-row-strong');
            const rowTime = el('div', 'imgc-row imgc-row-time');
            info.appendChild(rowOrig);
            info.appendChild(rowRes);
            info.appendChild(rowTime);
            body.appendChild(info);
            card.appendChild(body);

            const presets = el('div', 'imgc-presets');
            const presetBtns = presetList.map((p, i) => {
                const b = el('button', 'imgc-preset', null);
                b.type = 'button';
                b.appendChild(el('span', 'imgc-preset-label', p.label));
                b.appendChild(el('span', 'imgc-preset-hint', p.hint));
                b.addEventListener('click', () => {
                    if (busy || i === activePreset) return;
                    activePreset = i;
                    syncPresets();
                    recompute();
                });
                presets.appendChild(b);
                return b;
            });
            card.appendChild(presets);

            const actions = el('div', 'imgc-actions');
            const cancelBtn = el('button', 'imgc-btn imgc-btn-ghost', 'Отмена');
            cancelBtn.type = 'button';
            const sendBtn = el('button', 'imgc-btn imgc-btn-primary', 'Отправить');
            sendBtn.type = 'button';
            actions.appendChild(cancelBtn);
            actions.appendChild(sendBtn);
            card.appendChild(actions);

            rowOrig.textContent = 'Оригинал: ' + fmtSize(file.size);

            function syncPresets() {
                presetBtns.forEach((b, i) => b.classList.toggle('is-active', i === activePreset));
            }

            function setBusy(on) {
                busy = on;
                sendBtn.disabled = on || !current;
                presetBtns.forEach((b) => { b.disabled = on; });
            }

            function cleanup() {
                if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
                document.removeEventListener('keydown', onKey);
                overlay.remove();
            }

            function finish(value) {
                if (settled) return;
                settled = true;
                cleanup();
                resolve(value);
            }

            function onKey(e) {
                if (e.key === 'Escape') finish(null);
            }

            function setPreview(blob) {
                if (previewUrl) URL.revokeObjectURL(previewUrl);
                previewUrl = URL.createObjectURL(blob);
                thumb.src = previewUrl;
            }

            async function showOriginal() {
                setBusy(true);
                rowRes.textContent = 'Готовлю…';
                rowTime.textContent = '';
                badge.style.display = 'none';
                try {
                    const dims = await imageDims(file);
                    if (settled) return;
                    current = { original: true, blob: file, bytes: file.size, type: file.type, width: dims.w, height: dims.h };
                    setPreview(file);
                    badge.textContent = 'без сжатия';
                    badge.style.display = 'block';
                    rowRes.classList.remove('is-error');
                    rowRes.textContent = 'Как есть: ' + fmtSize(file.size) + ' · ' + dims.w + '×' + dims.h + ' · ' + fmtType(file.type);
                    rowTime.textContent = 'Передача ' + fmtTime(file.size / bps) + ' при ' + Math.round(bps) + ' Б/с';
                    sendBtn.disabled = false;
                } catch (e) {
                    current = null;
                    rowRes.textContent = 'Не удалось прочитать изображение';
                    rowRes.classList.add('is-error');
                } finally {
                    if (!settled) setBusy(false);
                }
            }

            async function showCompressed(target) {
                setBusy(true);
                rowRes.textContent = 'Сжимаю…';
                rowTime.textContent = '';
                badge.style.display = 'none';
                try {
                    const res = await ImageCompress.compressToBudget(file, target, { maxBase: 2000 });
                    if (settled) return;
                    current = res;
                    setPreview(res.blob);

                    const ratio = file.size / Math.max(1, res.bytes);
                    badge.textContent = 'в ' + ratio.toFixed(ratio >= 10 ? 0 : 1) + '× меньше';
                    badge.style.display = 'block';

                    rowRes.classList.toggle('is-error', res.bytes > maxBytes);
                    rowRes.textContent = 'Результат: ' + fmtSize(res.bytes) + ' · ' +
                        res.width + '×' + res.height + ' · ' + fmtType(res.type) +
                        ' · q' + res.quality.toFixed(2);

                    if (res.bytes > maxBytes) {
                        rowTime.textContent = 'Не влезает в лимит ' + fmtSize(maxBytes) + ' — выберите меньший размер';
                        sendBtn.disabled = true;
                    } else {
                        rowTime.textContent = 'Передача ' + fmtTime(res.bytes / bps) + ' при ' + Math.round(bps) + ' Б/с';
                        sendBtn.disabled = false;
                    }
                } catch (e) {
                    current = null;
                    rowRes.textContent = 'Не удалось сжать: ' + (e && e.message ? e.message : e);
                    rowRes.classList.add('is-error');
                } finally {
                    if (!settled) setBusy(false);
                }
            }

            function recompute() {
                const preset = presetList[activePreset];
                if (preset.original) return showOriginal();
                return showCompressed(preset.bytes);
            }

            cancelBtn.addEventListener('click', () => finish(null));
            overlay.addEventListener('click', (e) => { if (e.target === overlay) finish(null); });
            document.addEventListener('keydown', onKey);

            sendBtn.addEventListener('click', async () => {
                if (busy || !current) return;
                if (!current.original && current.bytes > maxBytes) return;
                setBusy(true);
                const buf = new Uint8Array(await current.blob.arrayBuffer());
                const name = current.original ? file.name : (stemOf(file.name) + '.' + current.ext);
                const meta = current.original
                    ? fmtSize(file.size) + ' · ' + current.width + '×' + current.height + ' · оригинал · без шифрования'
                    : fmtSize(file.size) + ' → ' + fmtSize(current.bytes) + ' · ' +
                        current.width + '×' + current.height + ' · ' + fmtType(current.type) + ' · без шифрования';
                finish({ name, bytes: buf, meta });
            });

            document.body.appendChild(overlay);
            syncPresets();
            recompute();
        });
    }

    return { open };
})();
