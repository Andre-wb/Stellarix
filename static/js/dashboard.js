// Работает с данными из HTML (серверный рендеринг) + localStorage для реального времени
document.addEventListener('DOMContentLoaded', () => {
    const ACCENT = '#5e9fe8';
    const ACCENT_DIM = 'rgba(94, 159, 232, 0.25)';
    const OK = '#72bc8f';
    const ERR = '#e97366';
    const GRID = 'rgba(255, 255, 255, 0.07)';
    const MUTED = 'rgba(255, 255, 255, 0.45)';
    const FONT = '10px ui-monospace, "Cascadia Mono", Consolas, monospace';

    const $ = (id) => document.getElementById(id);
    const pad = (n) => String(n).padStart(2, '0');

    const KIND_LABEL = { tx: 'Исходящая', rx: 'Входящая', key: 'Обмен ключами' };
    const DASH = '—';
    const PAGE_LOAD = Date.now();
    const serverRows = Array.isArray(window.dashboardSessions) ? window.dashboardSessions.slice() : [];

    function fmtTime(ts) {
        const d = new Date(ts);
        return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + ' ' +
            pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    }

    function fmtMs(ms) {
        if (ms == null || !isFinite(ms)) return '—';
        return ms >= 1000 ? (ms / 1000).toFixed(1).replace('.', ',') + ' с' : Math.round(ms) + ' мс';
    }

    function speedOf(s) {
        return (s.bytes && s.ms) ? Math.round((s.bytes * 8) / (s.ms / 1000)) : null;
    }

    function ctx2d(id) {
        const c = document.getElementById(id);
        if (!c) return null;
        const dpr = window.devicePixelRatio || 1;
        const w = c.clientWidth;
        const h = c.clientHeight;
        if (w < 10 || h < 10) return null;
        c.width = Math.round(w * dpr);
        c.height = Math.round(h * dpr);
        const ctx = c.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        return { ctx, w, h };
    }

    function placeholder(id) {
        const s = ctx2d(id);
        if (!s) return;
        const { ctx, w, h } = s;
        ctx.fillStyle = MUTED;
        ctx.font = FONT;
        ctx.textAlign = 'center';
        ctx.fillText('ожидание данных…', w / 2, h / 2);
        ctx.textAlign = 'left';
    }

    function grid(ctx, w, h, padL, padR, padT, padB, max) {
        ctx.strokeStyle = GRID;
        ctx.fillStyle = MUTED;
        ctx.font = FONT;
        ctx.lineWidth = 1;
        const ih = h - padT - padB;
        for (let g = 0; g <= 3; g++) {
            const y = padT + ih - (ih * g) / 3;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(w - padR, y);
            ctx.stroke();
            ctx.fillText(String(Math.round((max * g) / 3)), 2, y + 3);
        }
    }
    
    function drawLine(id, dataIn) {
        if (!dataIn || !dataIn.length) { placeholder(id); return; }
        const data = dataIn.length === 1 ? [dataIn[0], dataIn[0]] : dataIn;
        const s = ctx2d(id);
        if (!s) return;
        const { ctx, w, h } = s;
        const padL = 30, padR = 8, padT = 10, padB = 12;
        const max = (Math.max.apply(null, data) * 1.15) || 1;
        const iw = w - padL - padR;
        const ih = h - padT - padB;
        grid(ctx, w, h, padL, padR, padT, padB, max);

        const px = (i) => padL + (iw * i) / (data.length - 1);
        const py = (v) => padT + ih - (v / max) * ih;

        const grad = ctx.createLinearGradient(0, padT, 0, h - padB);
        grad.addColorStop(0, 'rgba(94, 159, 232, 0.28)');
        grad.addColorStop(1, 'rgba(94, 159, 232, 0)');
        ctx.beginPath();
        data.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
        ctx.lineTo(px(data.length - 1), padT + ih);
        ctx.lineTo(px(0), padT + ih);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();

        ctx.beginPath();
        data.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.stroke();

        ctx.fillStyle = ACCENT;
        ctx.beginPath();
        ctx.arc(px(data.length - 1), py(data[data.length - 1]), 3, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawBars(id, data, decimals) {
        if (!data || !data.length) { placeholder(id); return; }
        const s = ctx2d(id);
        if (!s) return;
        const { ctx, w, h } = s;
        const padL = 30, padR = 8, padT = 10, padB = 20;
        const max = (Math.max.apply(null, data) * 1.15) || 1;
        const iw = w - padL - padR;
        const ih = h - padT - padB;
        grid(ctx, w, h, padL, padR, padT, padB, max);

        const n = data.length;
        const bw = Math.min(26, (iw / n) * 0.55);
        ctx.font = FONT;
        data.forEach((v, i) => {
            const cx = padL + (iw * (i + 0.5)) / n;
            const bh = (v / max) * ih;
            const x = cx - bw / 2;
            const y = padT + ih - bh;
            ctx.fillStyle = i === n - 1 ? ACCENT : ACCENT_DIM;
            if (typeof ctx.roundRect === 'function') {
                ctx.beginPath();
                ctx.roundRect(x, y, bw, Math.max(1, bh), 4);
                ctx.fill();
            } else {
                ctx.fillRect(x, y, bw, Math.max(1, bh));
            }
            ctx.fillStyle = MUTED;
            ctx.textAlign = 'center';
            ctx.fillText(decimals != null ? v.toFixed(decimals) : String(v), cx, h - 6);
            ctx.textAlign = 'left';
        });
    }

    function drawDonut(id, okCount, errCount) {
        const total = okCount + errCount;
        if (!total) { placeholder(id); return; }
        const s = ctx2d(id);
        if (!s) return;
        const { ctx, w, h } = s;
        const cx = w / 2;
        const cy = h / 2;
        const R = Math.min(w, h) / 2 - 8;
        const r = R * 0.64;

        let a = -Math.PI / 2;
        [{ value: okCount, color: OK }, { value: errCount, color: ERR }].forEach((p) => {
            if (!p.value) return;
            const a2 = a + (p.value / total) * Math.PI * 2;
            const gapFix = total === p.value ? 0 : 0.02;
            ctx.beginPath();
            ctx.arc(cx, cy, R, a + gapFix, a2 - gapFix);
            ctx.arc(cx, cy, r, a2 - gapFix, a + gapFix, true);
            ctx.closePath();
            ctx.fillStyle = p.color;
            ctx.fill();
            a = a2;
        });

        ctx.textAlign = 'center';
        ctx.fillStyle = '#ffffff';
        ctx.font = '600 20px -apple-system, "Segoe UI", Roboto, sans-serif';
        ctx.fillText(Math.round((okCount / total) * 100) + '%', cx, cy + 1);
        ctx.fillStyle = MUTED;
        ctx.font = FONT;
        ctx.fillText('успех', cx, cy + 16);
        ctx.textAlign = 'left';
    }

    function toRow(entry) {
        const bytes = (typeof entry.bytes === 'number' && entry.bytes >= 0) ? entry.bytes : null;
        const ms = (typeof entry.ms === 'number' && entry.ms > 0) ? entry.ms : null;
        const speed = (bytes && ms) ? Math.round((bytes * 8) / (ms / 1000)) : null;
        return {
            time: fmtTime(entry.at),
            session_type: KIND_LABEL[entry.kind] || entry.kind || DASH,
            volume: bytes == null ? DASH : bytes + ' Б',
            duration: ms == null ? DASH : fmtMs(ms),
            speed: speed == null ? DASH : speed + ' бит/с',
            status: entry.ok ? 'Успешно' : 'Ошибка',
            ok: !!entry.ok,
            at: entry.at,
            kind: entry.kind,
            bytes: bytes,
            ms: ms,
        };
    }

    function liveRows() {
        if (typeof StxStats === 'undefined' || !StxStats.all) return [];
        return StxStats.all()
            .filter((entry) => entry && entry.at > PAGE_LOAD)
            .map(toRow)
            .reverse();
    }

    function allRows() {
        return liveRows().concat(serverRows);
    }

    let lastSig = null;

    function render(force) {
        const rows = allRows();
        const sig = rows.length + ':' + (rows.length ? rows[0].at : 0);
        if (!force && sig === lastSig) return;
        lastSig = sig;

        const chrono = rows.slice().reverse();
        const okCount = rows.filter((r) => r.ok).length;
        const errCount = rows.length - okCount;
        const speeds = chrono.filter((r) => r.ok).map(speedOf).filter((v) => v);

        $('stat-tx').textContent = String(rows.filter((r) => r.kind === 'tx').length);
        $('stat-rx').textContent = String(rows.filter((r) => r.kind === 'rx').length);
        $('stat-success').textContent = rows.length ? Math.round((okCount / rows.length) * 100) + '%' : DASH;
        $('stat-speed').textContent = speeds.length
            ? String(Math.round(speeds.reduce((a, b) => a + b, 0) / speeds.length))
            : DASH;

        drawLine('chart-speed', speeds.slice(-20));
        drawBars('chart-duration', chrono.filter((r) => r.ms).slice(-12).map((r) => r.ms / 1000), 1);
        drawBars('chart-bytes', chrono.filter((r) => r.bytes != null).slice(-12).map((r) => r.bytes), null);
        drawDonut('chart-donut', okCount, errCount);

        const legOk = $('leg-ok');
        const legErr = $('leg-err');
        if (legOk) legOk.textContent = 'Успешно · ' + okCount;
        if (legErr) legErr.textContent = 'Ошибки · ' + errCount;

        const tbody = $('sessions-tbody');
        if (tbody) {
            tbody.innerHTML = '';
            rows.slice(0, 12).forEach((r, idx) => {
                const tr = document.createElement('tr');
                if (idx === 0) tr.className = 'row-new';
                [r.time, r.session_type, r.volume, r.duration, r.speed].forEach((value) => {
                    const td = document.createElement('td');
                    td.textContent = value;
                    tr.appendChild(td);
                });
                const statusTd = document.createElement('td');
                const badge = document.createElement('span');
                badge.className = 'pill ' + (r.ok ? 'pill-ok' : 'pill-err');
                badge.textContent = r.status;
                statusTd.appendChild(badge);
                tr.appendChild(statusTd);
                tbody.appendChild(tr);
            });
        }

        const empty = $('dash-empty');
        const wrap = $('sessions-wrap');
        if (empty && wrap) {
            empty.style.display = rows.length ? 'none' : 'block';
            wrap.style.display = rows.length ? '' : 'none';
        }
    }

    render(true);
    setInterval(() => render(false), 1000);
    window.addEventListener('storage', () => render(true));

    let rt;
    window.addEventListener('resize', () => {
        clearTimeout(rt);
        rt = setTimeout(() => render(true), 150);
    });

    const resetBtn = $('stats-reset');
    if (resetBtn) {
        let resetArmed = false;
        let resetTimer = null;

        function disarmReset() {
            resetArmed = false;
            if (resetTimer) { clearTimeout(resetTimer); resetTimer = null; }
            resetBtn.textContent = 'Сбросить';
        }

        resetBtn.addEventListener('click', () => {
            if (typeof StxStats === 'undefined' || !StxStats.reset) return;
            if (!resetArmed) {
                resetArmed = true;
                resetBtn.textContent = 'Нажмите ещё раз';
                resetTimer = setTimeout(disarmReset, 4000);
                return;
            }
            disarmReset();
            StxStats.reset();
            render(true);
        });
    }
});