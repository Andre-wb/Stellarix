// Stellarix — фоновая звуковая волна (полосы с закруглёнными концами).
// API: SoundWave.attach(canvas), SoundWave.mode('idle'|'listen'|'transmit'), SoundWave.level(rms)
const SoundWave = (() => {
    let canvas = null;
    let ctx = null;
    let raf = null;
    let mode = 'idle';
    let targetLevel = 0; // сырой уровень от микрофона/передачи, затухает сам
    let t = 0;
    let levels = [];

    const BAR_W = 8;
    const GAP = 10;
    const MIN_BAR = 6;
    const MAX_RATIO = 0.72;
    const SMOOTH = 0.35;

    const COLORS = {
        idle: 'rgba(255, 255, 255, 0.75)',
        listen: 'rgba(255, 255, 255, 0.95)',
        transmit: 'rgba(94, 159, 232, 0.95)',
    };

    function resize() {
        if (!canvas || !ctx) return;
        const dpr = window.devicePixelRatio || 1;
        const r = canvas.getBoundingClientRect();
        canvas.width = Math.max(1, Math.round(r.width * dpr));
        canvas.height = Math.max(1, Math.round(r.height * dpr));
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function roundedBar(x, y, w, h, r) {
        if (typeof ctx.roundRect === 'function') {
            ctx.beginPath();
            ctx.roundRect(x, y, w, h, r);
            ctx.fill();
            return;
        }
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + w, y, x + w, y + h, r);
        ctx.arcTo(x + w, y + h, x, y + h, r);
        ctx.arcTo(x, y + h, x, y, r);
        ctx.arcTo(x, y, x + w, y, r);
        ctx.closePath();
        ctx.fill();
    }

    function draw() {
        raf = requestAnimationFrame(draw);
        if (!ctx || !canvas) return;
        const r = canvas.getBoundingClientRect();
        const W = r.width;
        const H = r.height;
        if (W < 2 || H < 2) return;
        t += 0.016;

        // затухание уровня, если новые значения не приходят
        targetLevel *= 0.955;

        const n = Math.max(16, Math.floor((W * 0.86) / (BAR_W + GAP)));
        if (levels.length !== n) levels = new Array(n).fill(0);

        let drive = Math.min(1, targetLevel * 4);
        if (mode === 'transmit') drive = Math.min(1, drive + 0.28 + 0.18 * Math.sin(t * 13));

        for (let i = 0; i < n; i++) {
            const x = n === 1 ? 0.5 : i / (n - 1);
            const envelope = Math.pow(Math.sin(Math.PI * x), 1.2);
            const w1 = Math.sin(x * 14 + t * 1.6);
            const w2 = Math.sin(x * 31 - t * 2.3);
            const w3 = Math.sin(x * 7 + t * 0.9);
            const v = 0.5 + 0.5 * (0.5 * w1 + 0.3 * w2 + 0.2 * w3);
            let target = envelope * (0.08 + 0.3 * v);
            if (drive > 0.001) {
                const flick = 0.75 + 0.25 * Math.sin(x * 47 + t * 21 + i);
                target = Math.min(1, target + envelope * drive * flick);
            }
            levels[i] += (target - levels[i]) * SMOOTH;
        }

        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = COLORS[mode] || COLORS.idle;

        const total = n * BAR_W + (n - 1) * GAP;
        const startX = (W - total) / 2;
        const mid = H / 2;
        const maxBar = H * MAX_RATIO;

        for (let i = 0; i < n; i++) {
            const h = Math.max(MIN_BAR, levels[i] * maxBar);
            roundedBar(startX + i * (BAR_W + GAP), mid - h / 2, BAR_W, h, BAR_W / 2);
        }
    }

    return {
        attach(el) {
            canvas = el;
            if (!canvas) return;
            ctx = canvas.getContext('2d');
            resize();
            window.addEventListener('resize', resize);
            if (!raf) draw();
        },
        mode(m) {
            if (m === 'idle' || m === 'listen' || m === 'transmit') mode = m;
        },
        level(v) {
            if (typeof v === 'number' && isFinite(v) && v >= 0) {
                targetLevel = Math.max(targetLevel, Math.min(1, v * 6));
            }
        },
        resize,
    };
})();
