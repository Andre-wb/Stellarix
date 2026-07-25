const ImageCompress = (() => {
    const IMAGE_EXT = /\.(png|jpe?g|webp|bmp|gif|avif|jfif)$/i;
    const SCALES = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.42, 0.35, 0.28, 0.22, 0.17, 0.13, 0.1, 0.07, 0.05];
    const Q_MIN = 0.3;
    const Q_MAX = 0.92;
    const Q_FLOOR = 0.55;

    function isImage(file) {
        if (!file) return false;
        const t = file.type || '';
        if (t === 'image/svg+xml') return false;
        if (t.startsWith('image/')) return true;
        return IMAGE_EXT.test(file.name || '');
    }

    async function decode(file) {
        if (window.createImageBitmap) {
            try {
                return await createImageBitmap(file, { imageOrientation: 'from-image' });
            } catch (e) {}
        }
        return await new Promise((resolve, reject) => {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('не удалось декодировать изображение')); };
            img.src = url;
        });
    }

    function dimsOf(src) {
        return { w: src.naturalWidth || src.width, h: src.naturalHeight || src.height };
    }

    function drawScaled(src, scale) {
        const { w, h } = dimsOf(src);
        const cw = Math.max(1, Math.round(w * scale));
        const ch = Math.max(1, Math.round(h * scale));
        const canvas = document.createElement('canvas');
        canvas.width = cw;
        canvas.height = ch;
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, cw, ch);
        ctx.drawImage(src, 0, 0, cw, ch);
        return { canvas, w: cw, h: ch };
    }

    function encode(canvas, type, quality) {
        return new Promise((resolve) => {
            canvas.toBlob((blob) => resolve(blob), type, quality);
        });
    }

    async function bestBlobAt(canvas, quality) {
        const jpeg = await encode(canvas, 'image/jpeg', quality);
        let webp = null;
        try {
            const w = await encode(canvas, 'image/webp', quality);
            if (w && w.type === 'image/webp') webp = w;
        } catch (e) {}
        if (webp && jpeg) return webp.size < jpeg.size ? webp : jpeg;
        return jpeg || webp;
    }

    async function refineQuality(canvas, target) {
        const top = await bestBlobAt(canvas, Q_MAX);
        if (top && top.size <= target) return { blob: top, quality: Q_MAX };
        let lo = Q_MIN;
        let hi = Q_MAX;
        let fit = null;
        let fitQ = Q_MIN;
        for (let i = 0; i < 7; i++) {
            const mid = (lo + hi) / 2;
            const blob = await bestBlobAt(canvas, mid);
            if (blob && blob.size <= target) { fit = blob; fitQ = mid; lo = mid; }
            else hi = mid;
        }
        if (fit) return { blob: fit, quality: fitQ };
        const floor = await bestBlobAt(canvas, Q_MIN);
        return { blob: floor, quality: Q_MIN };
    }

    async function compressToBudget(file, targetBytes, opts) {
        opts = opts || {};
        const maxBase = opts.maxBase || 2000;
        const src = await decode(file);
        try {
            const { w, h } = dimsOf(src);
            const longest = Math.max(w, h) || 1;
            const cap = Math.min(1, maxBase / longest);
            const scales = SCALES
                .map((s) => Math.max(s * cap, 1 / longest))
                .filter((s, i, a) => a.indexOf(s) === i);

            let chosen = scales[scales.length - 1];
            for (const s of scales) {
                const probe = drawScaled(src, s);
                const blob = await encode(probe.canvas, 'image/jpeg', Q_FLOOR);
                if (blob && blob.size <= targetBytes) { chosen = s; break; }
            }

            const drawn = drawScaled(src, chosen);
            const refined = await refineQuality(drawn.canvas, targetBytes);
            const type = refined.blob.type || 'image/jpeg';
            return {
                blob: refined.blob,
                bytes: refined.blob.size,
                width: drawn.w,
                height: drawn.h,
                quality: refined.quality,
                type,
                ext: type === 'image/webp' ? 'webp' : 'jpg',
                sourceWidth: w,
                sourceHeight: h,
            };
        } finally {
            if (src.close) src.close();
        }
    }

    return { isImage, compressToBudget };
})();
