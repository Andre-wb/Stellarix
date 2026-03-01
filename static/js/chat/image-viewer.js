export function openImageViewer(url, name) {
    document.getElementById('image-viewer-img').src = url;
    document.getElementById('image-viewer-name').textContent = name;
    document.getElementById('image-viewer-overlay').classList.add('show');
}

export function closeImageViewer() {
    document.getElementById('image-viewer-overlay').classList.remove('show');
    document.getElementById('image-viewer-img').src = '';
}

export function initImageViewer() {
    const img  = document.getElementById('image-viewer-img');
    const dlEl = document.getElementById('image-viewer-download');

    new MutationObserver(() => {
        if (img.src) {
            dlEl.href     = img.src;
            dlEl.download = document.getElementById('image-viewer-name').textContent;
        }
    }).observe(img, { attributes: true, attributeFilter: ['src'] });

    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        if (document.getElementById('image-viewer-overlay').classList.contains('show'))
            closeImageViewer();
        if (document.getElementById('file-preview-overlay').classList.contains('show'))
            window.cancelFilePreview();
    });
}