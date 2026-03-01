const _ivImg = document.getElementById('image-viewer-img');
const _ivDl  = document.getElementById('image-viewer-download');
new MutationObserver(() => {
    if (_ivImg.src) { _ivDl.href = _ivImg.src; _ivDl.download = document.getElementById('image-viewer-name').textContent; }
}).observe(_ivImg, { attributes: true, attributeFilter: ['src'] });
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        if (document.getElementById('image-viewer-overlay').classList.contains('show')) window.closeImageViewer();
        if (document.getElementById('file-preview-overlay').classList.contains('show')) window.cancelFilePreview();
    }
});