const Avatar = (() => {
    const OWN_KEY = 'stx_avatar';
    const PEER_KEY = 'stx_peer_avatar';
    const PEER_NAME_KEY = 'stx_peer_name';
    const NAME_MAX_CHARS = 64;
    const MAGIC_HEX = '53545841563100';
    const TARGET_BYTES = 2200;
    const SIZES = [96, 80, 64, 48];
    const QUALITIES = [0.72, 0.62, 0.52, 0.44, 0.38];

    function read(key) {
        try { return localStorage.getItem(key) || ''; } catch (e) { return ''; }
    }
    function write(key, value) {
        try {
            if (value) localStorage.setItem(key, value);
            else localStorage.removeItem(key);
        } catch (e) {}
    }

    function getOwn() { return read(OWN_KEY); }
    function setOwn(dataUrl) { write(OWN_KEY, dataUrl); }
    function clearOwn() { write(OWN_KEY, ''); }
    function getPeer() { return read(PEER_KEY); }
    function setPeer(dataUrl) { write(PEER_KEY, dataUrl); }
    function clearPeer() { write(PEER_KEY, ''); }
    function getPeerName() { return read(PEER_NAME_KEY); }
    function setPeerName(name) { write(PEER_NAME_KEY, (name || '').trim()); }
    function clearPeerName() { write(PEER_NAME_KEY, ''); }

    function letter(name) {
        const s = (name || '').trim();
        if (!s) return '?';
        return s.charAt(0).toUpperCase();
    }

    function peerLetter() { return letter(getPeerName()); }

    function render(el, dataUrl, fallbackLetter) {
        if (!el) return;
        if (dataUrl) {
            el.textContent = '';
            el.style.backgroundImage = 'url("' + dataUrl + '")';
            el.classList.add('avatar-has-img');
        } else {
            el.style.backgroundImage = '';
            el.classList.remove('avatar-has-img');
            el.textContent = fallbackLetter || '';
        }
    }

    function bytesToHex(bytes) {
        let out = '';
        for (let i = 0; i < bytes.length; i++) out += bytes[i].toString(16).padStart(2, '0');
        return out;
    }
    function hexToBytes(hex) {
        const clean = (hex || '').trim();
        const out = new Uint8Array(clean.length / 2);
        for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.substr(i * 2, 2), 16);
        return out;
    }

    function sniffMime(bytes) {
        if (bytes.length > 2 && bytes[0] === 0xff && bytes[1] === 0xd8) return 'image/jpeg';
        if (bytes.length > 3 && bytes[0] === 0x89 && bytes[1] === 0x50) return 'image/png';
        if (bytes.length > 11 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[8] === 0x57 && bytes[9] === 0x45) return 'image/webp';
        return 'image/jpeg';
    }

    function bytesToDataUrl(bytes) {
        if (!bytes || !bytes.length) return '';
        let bin = '';
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
        return 'data:' + sniffMime(bytes) + ';base64,' + btoa(bin);
    }

    function dataUrlToBytes(dataUrl) {
        const comma = (dataUrl || '').indexOf(',');
        if (comma < 0) return new Uint8Array(0);
        const bin = atob(dataUrl.slice(comma + 1));
        const out = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
        return out;
    }

    async function decode(file) {
        if (window.createImageBitmap) {
            try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch (e) {}
        }
        return await new Promise((resolve, reject) => {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('не удалось декодировать изображение')); };
            img.src = url;
        });
    }

    function encode(canvas, quality) {
        return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/jpeg', quality));
    }

    function blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error('не удалось прочитать изображение'));
            reader.readAsDataURL(blob);
        });
    }

    function squareCanvas(src, size) {
        const w = src.naturalWidth || src.width;
        const h = src.naturalHeight || src.height;
        const side = Math.min(w, h);
        const sx = Math.max(0, (w - side) / 2);
        const sy = Math.max(0, (h - side) / 2);
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, size, size);
        ctx.drawImage(src, sx, sy, side, side, 0, 0, size, size);
        return canvas;
    }

    async function compressFile(file) {
        const src = await decode(file);
        try {
            let last = null;
            for (const size of SIZES) {
                const canvas = squareCanvas(src, size);
                for (const q of QUALITIES) {
                    const blob = await encode(canvas, q);
                    if (!blob) continue;
                    last = blob;
                    if (blob.size <= TARGET_BYTES) return await blobToDataUrl(blob);
                }
            }
            if (last) return await blobToDataUrl(last);
            throw new Error('не удалось сжать изображение');
        } finally {
            if (src.close) src.close();
        }
    }

    function nameToBytes(name) {
        const s = (name || '').trim().slice(0, NAME_MAX_CHARS);
        return new TextEncoder().encode(s);
    }
    function bytesToName(bytes) {
        try { return new TextDecoder().decode(bytes); } catch (e) { return ''; }
    }

    function profileHex(name) {
        const nameBytes = nameToBytes(name);
        const own = getOwn();
        const avatarBytes = own ? dataUrlToBytes(own) : new Uint8Array(0);
        const out = new Uint8Array(1 + nameBytes.length + avatarBytes.length);
        out[0] = nameBytes.length;
        out.set(nameBytes, 1);
        out.set(avatarBytes, 1 + nameBytes.length);
        return bytesToHex(out);
    }

    function parseProfileHex(hex) {
        if (!hex) return { name: '', avatar: '' };
        const bytes = hexToBytes(hex);
        if (!bytes.length) return { name: '', avatar: '' };
        const nameLen = bytes[0];
        const name = bytesToName(bytes.slice(1, 1 + nameLen));
        const avatarBytes = bytes.slice(1 + nameLen);
        return { name, avatar: avatarBytes.length ? bytesToDataUrl(avatarBytes) : '' };
    }

    function updateMsgHex(name) {
        return MAGIC_HEX + profileHex(name);
    }

    function isUpdateHex(hex) {
        return typeof hex === 'string' && hex.toLowerCase().startsWith(MAGIC_HEX);
    }

    function profileFromUpdateHex(hex) {
        return parseProfileHex(hex.slice(MAGIC_HEX.length));
    }

    function isImageFile(file) {
        if (!file) return false;
        const t = file.type || '';
        if (t === 'image/svg+xml') return false;
        if (t.startsWith('image/')) return true;
        return /\.(png|jpe?g|webp|bmp|gif|avif|jfif)$/i.test(file.name || '');
    }

    return {
        MAGIC_HEX,
        getOwn, setOwn, clearOwn,
        getPeer, setPeer, clearPeer,
        getPeerName, setPeerName, clearPeerName,
        letter, peerLetter, render,
        bytesToHex, hexToBytes, bytesToDataUrl, dataUrlToBytes,
        compressFile, isImageFile,
        profileHex, parseProfileHex, updateMsgHex, isUpdateHex, profileFromUpdateHex,
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = Avatar;
}
