import { fmtSize, getCookie } from '../utils.js';

let _pendingFile     = null;
let _resizedBlob     = null;
let _origW           = 0;
let _origH           = 0;
let _origDataUrl     = null;
let _skipCompression = false;

const $ = id => document.getElementById(id);

export function uploadFile(e) {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;

    _pendingFile     = file;
    _resizedBlob     = null;
    _skipCompression = false;
    _origDataUrl     = null;

    const isImage = file.type.startsWith('image/');

    if (isImage) {
        const reader = new FileReader();
        reader.onload = ev => {
            _origDataUrl = ev.target.result;
            const img    = new Image();
            img.onload   = () => {
                _origW = img.naturalWidth;
                _origH = img.naturalHeight;

                $('preview-img').src           = _origDataUrl;
                $('preview-img').style.display = 'block';
                $('preview-file-card').style.display = 'none';

                $('fpo-filename').textContent = file.name;
                $('fpo-filesize').textContent = fmtSize(file.size);

                _showCompressionSection(100);
                _updateCompressionInfo(100);
            };
            img.src = _origDataUrl;
        };
        reader.readAsDataURL(file);
    } else {
        const icon = file.type.startsWith('video/') ? '🎬'
            : file.type.startsWith('audio/') ? '🎵' : '📄';

        $('preview-img').style.display        = 'none';
        $('preview-file-card').style.display  = 'flex';
        $('fpo-file-icon').textContent  = icon;
        $('fpo-file-name').textContent  = file.name;
        $('fpo-file-size').textContent  = fmtSize(file.size);
        $('fpo-filename').textContent   = file.name;
        $('fpo-filesize').textContent   = fmtSize(file.size);

        $('compress-section').style.display = 'none';
    }

    $('file-preview-overlay').classList.add('show');
    closeDotMenu();
}

function _showCompressionSection(pct) {
    const sec = $('compress-section');
    if (!sec) return;
    sec.style.display = 'block';
    const slider = $('compress-slider');
    if (slider) slider.value = pct;
}

export function onCompressSlider(val) {
    if (_skipCompression) return;
    const pct = parseInt(val, 10);
    _updateCompressionInfo(pct);
    _applyCompression(pct);
}

function _updateCompressionInfo(pct) {
    const w     = Math.round(_origW * pct / 100);
    const h     = Math.round(_origH * pct / 100);
    const label = $('compress-dims');
    if (label) label.textContent = `${w} × ${h}`;
    const pctLabel = $('compress-pct');
    if (pctLabel) pctLabel.textContent = pct + '%';

    if (pct < 100 && _pendingFile) {
        const estimatedSize = Math.round(_pendingFile.size * (pct / 100) * 0.7);
        const sizeLabel = $('fpo-filesize');
        if (sizeLabel) sizeLabel.textContent = '~' + fmtSize(estimatedSize);
    } else if (_pendingFile) {
        const sizeLabel = $('fpo-filesize');
        if (sizeLabel) sizeLabel.textContent = fmtSize(_pendingFile.size);
    }
}

function _applyCompression(pct) {
    if (!_pendingFile || !_pendingFile.type.startsWith('image/') || !_origDataUrl) return;
    if (pct >= 100) {
        _resizedBlob = null;
        $('preview-img').src = _origDataUrl;
        if ($('fpo-filesize')) $('fpo-filesize').textContent = fmtSize(_pendingFile.size);
        return;
    }

    const w = Math.round(_origW * pct / 100);
    const h = Math.round(_origH * pct / 100);

    const img   = new Image();
    img.onload  = () => {
        const canvas    = document.createElement('canvas');
        canvas.width    = w;
        canvas.height   = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob(blob => {
            if (!blob) return;
            _resizedBlob = blob;
            const url    = URL.createObjectURL(blob);
            $('preview-img').src = url;
            if ($('fpo-filesize')) $('fpo-filesize').textContent = fmtSize(blob.size);
        }, _pendingFile.type.includes('png') ? 'image/png' : 'image/jpeg', 0.92);
    };
    img.src = _origDataUrl;
}

export function toggleDotMenu() {
    const menu = $('fpo-dot-menu');
    if (!menu) return;
    menu.classList.toggle('show');
}

export function closeDotMenu() {
    $('fpo-dot-menu')?.classList.remove('show');
}

export function sendWithoutCompression() {
    _skipCompression = true;
    _resizedBlob     = null;

    const slider = $('compress-slider');
    if (slider) { slider.value = 100; slider.disabled = true; }

    $('compress-section').style.opacity = '0.4';
    $('compress-section').style.pointerEvents = 'none';

    if (_pendingFile) {
        $('fpo-filesize').textContent = fmtSize(_pendingFile.size);
        if (_origDataUrl) $('preview-img').src = _origDataUrl;
    }
    if ($('compress-dims')) $('compress-dims').textContent = `${_origW} × ${_origH}`;
    if ($('compress-pct'))  $('compress-pct').textContent  = '100%';

    const sendBtn = $('fpo-send-btn');
    if (sendBtn) sendBtn.textContent = '↑ Отправить (без сжатия)';

    closeDotMenu();
}

export function cancelFilePreview() {
    if ($('file-preview-overlay')?.classList.contains('uploading')) return;
    _pendingFile     = null;
    _resizedBlob     = null;
    _origDataUrl     = null;
    _skipCompression = false;

    $('file-preview-overlay').classList.remove('show');
    $('preview-img').src           = '';
    $('preview-img').style.display = 'none';
    $('compress-section').style.display = 'none';
    const slider = $('compress-slider');
    if (slider) slider.disabled = false;
    const sec = $('compress-section');
    if (sec) { sec.style.opacity = ''; sec.style.pointerEvents = ''; }

    closeDotMenu();
    _resetSendBtn();
}

export async function sendPendingFile() {
    if (!_pendingFile) return;
    const S = window.AppState;
    if (!S.currentRoom?.id) return;

    const csrfToken = S.csrfToken || getCookie('csrf_token');
    if (!csrfToken) {
        _showError('CSRF токен не найден — обновите страницу.');
        return;
    }

    _setUploading(true);

    const blobToSend = (_resizedBlob && !_skipCompression) ? _resizedBlob : _pendingFile;
    const fileName   = _pendingFile.name;
    const mimeType   = _pendingFile.type;

    const formData = new FormData();
    formData.append('file', new File([blobToSend], fileName, { type: mimeType }));

    try {
        const response = await fetch(`/api/files/upload/${S.currentRoom.id}`, {
            method:      'POST',
            credentials: 'include',
            headers:     { 'X-CSRF-Token': csrfToken },
            body:        formData,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || err.error || `HTTP ${response.status}`);
        }

        const sendBtn = $('fpo-send-btn');
        if (sendBtn) {
            sendBtn.textContent = '✓ Отправлено';
            sendBtn.style.background = 'var(--green)';
        }
        setTimeout(cancelFilePreview, 700);

    } catch (err) {
        _setUploading(false);
        _showError(err.message);
    }
}

export function triggerFileUpload() {
    $('file-input').click();
}

function _setUploading(on) {
    const overlay   = $('file-preview-overlay');
    const sendBtn   = $('fpo-send-btn');
    const cancelBtn = $('fpo-cancel-btn');

    if (on) {
        overlay?.classList.add('uploading');
        if (sendBtn) {
            sendBtn.disabled    = true;
            sendBtn.innerHTML   = '<span class="upload-spinner"></span>Загрузка...';
        }
        if (cancelBtn) { cancelBtn.disabled = true; cancelBtn.style.opacity = '0.4'; }
    } else {
        overlay?.classList.remove('uploading');
        _resetSendBtn();
        if (cancelBtn) { cancelBtn.disabled = false; cancelBtn.style.opacity = ''; }
    }
}

function _resetSendBtn() {
    const btn = $('fpo-send-btn');
    if (!btn) return;
    btn.disabled    = false;
    btn.style.background = '';
    btn.innerHTML   = '↑ Отправить';
}

function _showError(msg) {
    let el = $('fpo-error');
    if (!el) {
        el    = document.createElement('div');
        el.id = 'fpo-error';
        el.style.cssText = [
            'font-size:12px', 'color:var(--red)', 'font-family:var(--mono)',
            'padding:8px 24px', 'text-align:center', 'display:none',
        ].join(';');
        $('file-preview-overlay')?.insertBefore(el, $('fpo-bottom-bar'));
    }
    el.textContent = '⚠ ' + msg;
    el.style.display = 'block';
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.display = 'none'; }, 6000);
}