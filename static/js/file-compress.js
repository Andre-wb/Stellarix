const FileCompress = (() => {
    function supported() {
        return typeof CompressionStream !== 'undefined';
    }

    async function gzipSize(file) {
        const stream = file.stream().pipeThrough(new CompressionStream('gzip'));
        const reader = stream.getReader();
        let total = 0;
        for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            total += value.byteLength;
        }
        return total;
    }

    async function estimate(file) {
        const raw = file.size;
        const compressed = Math.min(raw, await gzipSize(file));
        return { raw, compressed, ratio: raw > 0 ? raw / compressed : 1 };
    }

    return { supported, estimate };
})();
