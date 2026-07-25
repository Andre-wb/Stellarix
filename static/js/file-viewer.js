(function () {
    function byId(id) { return document.getElementById(id); }

    function openFileViewer(name, url, text) {
        const overlay = byId('file-viewer-overlay');
        if (!overlay) return;
        byId('file-viewer-name').textContent = name || '';
        const body = byId('file-viewer-body');
        const note = byId('file-viewer-note');
        if (text != null) {
            body.textContent = text;
            body.style.display = '';
            note.style.display = 'none';
        } else {
            body.textContent = '';
            body.style.display = 'none';
            note.style.display = '';
        }
        const dl = byId('file-viewer-download');
        dl.href = url;
        dl.download = name || 'file';
        overlay.classList.add('show');
    }

    function closeFileViewer() {
        const overlay = byId('file-viewer-overlay');
        if (!overlay) return;
        overlay.classList.remove('show');
        byId('file-viewer-body').textContent = '';
    }

    function initFileViewer() {
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            const overlay = byId('file-viewer-overlay');
            if (overlay && overlay.classList.contains('show')) closeFileViewer();
        });
    }

    window.openFileViewer = openFileViewer;
    window.closeFileViewer = closeFileViewer;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFileViewer);
    } else {
        initFileViewer();
    }
})();
