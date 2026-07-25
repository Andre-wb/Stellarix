(function () {
    function byId(id) { return document.getElementById(id); }

    function openImageViewer(url, name) {
        const img = byId('image-viewer-img');
        if (!img) return;
        img.src = url;
        byId('image-viewer-name').textContent = name || '';
        byId('image-viewer-overlay').classList.add('show');
    }

    function closeImageViewer() {
        const overlay = byId('image-viewer-overlay');
        if (!overlay) return;
        overlay.classList.remove('show');
        byId('image-viewer-img').src = '';
    }

    function initImageViewer() {
        const img = byId('image-viewer-img');
        const dlEl = byId('image-viewer-download');
        if (!img || !dlEl) return;

        new MutationObserver(() => {
            if (img.src) {
                dlEl.href = img.src;
                dlEl.download = byId('image-viewer-name').textContent;
            }
        }).observe(img, { attributes: true, attributeFilter: ['src'] });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (byId('image-viewer-overlay').classList.contains('show')) closeImageViewer();
        });
    }

    window.openImageViewer = openImageViewer;
    window.closeImageViewer = closeImageViewer;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initImageViewer);
    } else {
        initImageViewer();
    }
})();
