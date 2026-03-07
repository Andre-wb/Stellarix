// static/js/chat/file-upload.js
// =============================================================================
// Модуль загрузки файлов в чат.
// Управляет предпросмотром, сжатием изображений, отправкой через XHR,
// отображением прогресса и обработкой ошибок.
//
// Улучшения (критерий 5 — возобновление загрузки):
//   • Файлы > RESUMABLE_THRESHOLD (2МБ) загружаются чанками через
//     протокол resumable: /api/files/upload-init → /api/files/upload-chunk → complete
//   • Прогресс сохраняется в localStorage: при перезагрузке страницы
//     незавершённую загрузку можно возобновить
//   • Каждый чанк проверяется SHA-256 хешем
//   • Ограничение параллелизма: не более 3 чанков одновременно
// =============================================================================

import { fmtSize, getCookie } from '../utils.js';

// ── Константы ─────────────────────────────────────────────────────────────────
const CHUNK_SIZE          = 1 * 1024 * 1024;   // 1 МБ
const RESUMABLE_THRESHOLD = 2 * 1024 * 1024;   // файлы > 2 МБ → чанкованная загрузка
const MAX_PARALLEL_CHUNKS = 3;                  // параллельные загрузки чанков
const CHUNK_RETRY_MAX     = 3;                  // повторы при ошибке чанка
const LS_KEY_PREFIX       = 'vortex_upload_';   // префикс localStorage

// ── Приватное состояние ───────────────────────────────────────────────────────
let _pendingFile     = null;
let _resizedBlob     = null;
let _origW           = 0;
let _origH           = 0;
let _origDataUrl     = null;
let _skipCompression = false;

// Состояние активной resumable-сессии (если есть)
let _resumeSession = null;  // { upload_id, total_chunks, received: Set }

const $ = id => document.getElementById(id);

// =============================================================================
// Вычисление SHA-256 через Web Crypto API
// =============================================================================

async function sha256Hex(buffer) {
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    return Array.from(new Uint8Array(hashBuffer))
        .map(b => b.toString(16).padStart(2, '0')).join('');
}

// =============================================================================
// Сохранение/восстановление прогресса в localStorage
// =============================================================================

function _saveProgress(uploadId, data) {
    try {
        localStorage.setItem(LS_KEY_PREFIX + uploadId, JSON.stringify(data));
    } catch {}
}

function _loadProgress(uploadId) {
    try {
        const raw = localStorage.getItem(LS_KEY_PREFIX + uploadId);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function _clearProgress(uploadId) {
    try { localStorage.removeItem(LS_KEY_PREFIX + uploadId); } catch {}
}

function _findExistingSession(fileName, fileSize) {
    // Ищем незавершённые сессии для этого файла
    try {
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (!key?.startsWith(LS_KEY_PREFIX)) continue;
            const data = JSON.parse(localStorage.getItem(key) || '{}');
            if (data.file_name === fileName && data.file_size === fileSize) {
                return { upload_id: key.slice(LS_KEY_PREFIX.length), ...data };
            }
        }
    } catch {}
    return null;
}

// =============================================================================
// Resumable upload — основная логика
// =============================================================================

/**
 * Загружает файл с поддержкой возобновления.
 * Для маленьких файлов (< RESUMABLE_THRESHOLD) использует обычный XHR.
 * Для больших — протокол чанков.
 *
 * @param {File|Blob} fileOrBlob - файл для загрузки
 * @param {string} fileName - имя файла
 * @param {number} roomId
 * @param {string} csrfToken
 * @param {function(number)} onProgress - колбэк прогресса (0-100)
 * @returns {Promise<object>} - ответ сервера
 */
async function uploadFileResumable(fileOrBlob, fileName, roomId, csrfToken, onProgress) {
    const fileSize = fileOrBlob.size;

    if (fileSize < RESUMABLE_THRESHOLD) {
        // Маленький файл — обычная загрузка
        const formData = new FormData();
        formData.append('file', new File([fileOrBlob], fileName, { type: fileOrBlob.type }));
        return _xhrUpload(`/api/files/upload/${roomId}`, formData, csrfToken, onProgress);
    }

    // ── Крупный файл — чанкованная загрузка ───────────────────────────────────
    const fileBuffer = await fileOrBlob.arrayBuffer();
    const fileHash   = await sha256Hex(fileBuffer);

    const totalChunks = Math.ceil(fileSize / CHUNK_SIZE);

    // Проверяем, есть ли незавершённая сессия для этого файла
    let uploadId    = null;
    let receivedSet = new Set();
    const existing  = _findExistingSession(fileName, fileSize);

    if (existing) {
        // Пытаемся возобновить
        console.info(`[Resumable] Найдена незавершённая сессия ${existing.upload_id}, возобновляем…`);
        try {
            const statusResp = await fetch(`/api/files/upload-status/${existing.upload_id}`, {
                credentials: 'include',
            });
            if (statusResp.ok) {
                const statusData = await statusResp.json();
                if (!statusData.complete) {
                    uploadId    = existing.upload_id;
                    receivedSet = new Set(statusData.received || []);
                    console.info(`[Resumable] Уже загружено ${receivedSet.size}/${totalChunks} чанков`);
                } else {
                    _clearProgress(existing.upload_id);
                }
            }
        } catch (e) {
            console.warn('[Resumable] Не удалось проверить сессию:', e.message);
        }
    }

    // Если сессии нет или она недействительна — инициализируем новую
    if (!uploadId) {
        const initForm = new FormData();
        initForm.append('room_id',   roomId);
        initForm.append('file_name', fileName);
        initForm.append('file_size', fileSize);
        initForm.append('file_hash', fileHash);
        initForm.append('chunk_size', CHUNK_SIZE);

        const initResp = await fetch('/api/files/upload-init', {
            method:      'POST',
            body:        initForm,
            credentials: 'include',
            headers:     { 'X-CSRF-Token': csrfToken },
        });
        if (!initResp.ok) {
            throw new Error(`Ошибка инициализации загрузки: HTTP ${initResp.status}`);
        }
        const initData = await initResp.json();
        uploadId       = initData.upload_id;
        receivedSet    = new Set(initData.received || []);

        // Сохраняем прогресс в localStorage
        _saveProgress(uploadId, { file_name: fileName, file_size: fileSize, file_hash: fileHash });
        console.info(`[Resumable] Новая сессия ${uploadId}, чанков: ${totalChunks}`);
    }

    _resumeSession = { upload_id: uploadId, total_chunks: totalChunks, received: receivedSet };

    // ── Загрузка чанков с ограничением параллелизма ────────────────────────────
    const pending = [];
    for (let i = 0; i < totalChunks; i++) {
        if (!receivedSet.has(i)) pending.push(i);
    }

    let completed = receivedSet.size;

    const uploadChunk = async (chunkIdx) => {
        const start    = chunkIdx * CHUNK_SIZE;
        const end      = Math.min(start + CHUNK_SIZE, fileSize);
        const chunkBuf = fileBuffer.slice(start, end);
        const chunkHash = await sha256Hex(chunkBuf);

        for (let attempt = 0; attempt < CHUNK_RETRY_MAX; attempt++) {
            const form = new FormData();
            form.append('chunk_index', chunkIdx);
            form.append('chunk_hash',  chunkHash);
            form.append('data',        new Blob([chunkBuf]));

            try {
                const resp = await fetch(`/api/files/upload-chunk/${uploadId}`, {
                    method:      'PUT',
                    body:        form,
                    credentials: 'include',
                    headers:     { 'X-CSRF-Token': csrfToken },
                });
                if (resp.ok) {
                    completed++;
                    receivedSet.add(chunkIdx);
                    const pct = Math.round(completed / totalChunks * 95);   // 95% = загрузка, 5% = сборка
                    onProgress(pct);
                    return;
                }
                const err = await resp.json().catch(() => ({}));
                console.warn(`[Resumable] Чанк ${chunkIdx} attempt ${attempt+1} failed:`, err);
            } catch (e) {
                console.warn(`[Resumable] Чанк ${chunkIdx} сетевая ошибка (попытка ${attempt+1}):`, e.message);
            }
            await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));   // exponential backoff
        }
        throw new Error(`Чанк ${chunkIdx} не загружен после ${CHUNK_RETRY_MAX} попыток`);
    };

    // Semaphore для параллелизма
    const semaphore = async (tasks, limit) => {
        const results = [];
        const executing = new Set();
        for (const task of tasks) {
            const p = Promise.resolve().then(task).finally(() => executing.delete(p));
            results.push(p);
            executing.add(p);
            if (executing.size >= limit) {
                await Promise.race(executing);
            }
        }
        return Promise.all(results);
    };

    await semaphore(
        pending.map(idx => () => uploadChunk(idx)),
        MAX_PARALLEL_CHUNKS
    );

    onProgress(97);

    // ── Финализация ─────────────────────────────────────────────────────────────
    const completeResp = await fetch(`/api/files/upload-complete/${uploadId}`, {
        method:      'POST',
        credentials: 'include',
        headers:     { 'X-CSRF-Token': csrfToken },
    });

    if (!completeResp.ok) {
        const errData = await completeResp.json().catch(() => ({}));
        throw new Error(errData.error || errData.detail || `Ошибка сборки: HTTP ${completeResp.status}`);
    }

    _clearProgress(uploadId);
    _resumeSession = null;
    onProgress(100);

    return await completeResp.json();
}

// =============================================================================
// Обработчик выбора файла
// =============================================================================

export function uploadFile(e) {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;

    _pendingFile     = file;
    _resizedBlob     = null;
    _skipCompression = false;
    _origDataUrl     = null;
    _origW           = 0;
    _origH           = 0;

    _resetSendBtn();
    const slider = $('compress-slider');
    if (slider) { slider.disabled = false; slider.value = 100; }
    const sec = $('compress-section');
    if (sec) { sec.style.opacity = ''; sec.style.pointerEvents = ''; sec.style.display = 'none'; }
    const errEl = $('fpo-error');
    if (errEl) errEl.style.display = 'none';

    $('fpo-filename').textContent = file.name;
    $('fpo-filesize').textContent = fmtSize(file.size);

    // Если файл большой — показываем значок возобновляемой загрузки
    if (file.size >= RESUMABLE_THRESHOLD) {
        const label = $('fpo-filesize');
        if (label) label.textContent = fmtSize(file.size) + ' · чанковая загрузка';
    }

    // Проверяем незавершённые сессии
    const existingSession = _findExistingSession(file.name, file.size);
    if (existingSession) {
        const progress = _loadProgress(existingSession.upload_id);
        if (progress) {
            _showResumeNotice(existingSession.upload_id, file.size);
        }
    }

    const isImage = file.type.startsWith('image/');

    if (isImage) {
        $('preview-img').style.display       = 'none';
        $('preview-img').src                 = '';
        $('preview-file-card').style.display = 'none';

        $('file-preview-overlay').classList.add('show');
        closeDotMenu();

        const reader = new FileReader();
        reader.onerror = () => _showAsFileCard('🖼', file.name, file.size);
        reader.onload  = ev => {
            _origDataUrl = ev.target.result;
            const img = new Image();
            img.onload = () => {
                _origW = img.naturalWidth;
                _origH = img.naturalHeight;
                $('preview-img').src           = _origDataUrl;
                $('preview-img').style.display = 'block';
                $('preview-file-card').style.display = 'none';
                $('fpo-filesize').textContent  = fmtSize(file.size);
                _showCompressionSection(100);
                _updateCompressionInfo(100);
                _showEditPhotoBtn(true);
            };
            img.onerror = () => _showAsFileCard('🖼', file.name, file.size);
            img.src = _origDataUrl;
        };
        reader.readAsDataURL(file);
    } else {
        const icon = file.type.startsWith('video/') ? '🎬'
            : file.type.startsWith('audio/') ? '🎵'
                : '📄';
        _showAsFileCard(icon, file.name, file.size);
        $('compress-section').style.display = 'none';
        $('file-preview-overlay').classList.add('show');
        closeDotMenu();
        _showEditPhotoBtn(false);
    }
}

/** Показывает уведомление о возможности возобновить загрузку */
function _showResumeNotice(uploadId, fileSize) {
    let notice = $('fpo-resume-notice');
    if (!notice) {
        notice = document.createElement('div');
        notice.id = 'fpo-resume-notice';
        notice.style.cssText = [
            'background:rgba(78,205,196,.1)', 'border:1px solid rgba(78,205,196,.3)',
            'border-radius:8px', 'padding:8px 12px', 'font-size:12px',
            'color:#4ecdc4', 'margin:8px 16px', 'display:flex', 'align-items:center', 'gap:8px',
        ].join(';');
        const actions = document.querySelector('.fpo-actions');
        if (actions) actions.parentNode.insertBefore(notice, actions);
    }
    notice.innerHTML =
        `⏩ Найдена незавершённая загрузка этого файла. ` +
        `<button onclick="window._resumeUpload && window._resumeUpload('${uploadId}')" ` +
        `style="background:none;border:none;color:#4ecdc4;cursor:pointer;text-decoration:underline;padding:0">Возобновить</button>`;
    notice.style.display = 'flex';
}

// =============================================================================
// Отправка файла
// =============================================================================

export async function sendPendingFile() {
    if (!_pendingFile) return;
    const S = window.AppState;
    if (!S?.currentRoom?.id) return;

    const csrfToken = S.csrfToken || getCookie('csrf_token');
    if (!csrfToken) { _showError('CSRF токен не найден — обновите страницу.'); return; }

    const blobToSend = (_resizedBlob && !_skipCompression) ? _resizedBlob : _pendingFile;
    const fileName   = _pendingFile.name;
    const mimeType   = _pendingFile.type;
    const localSrc   = _origDataUrl || null;

    $('file-preview-overlay')?.classList.remove('uploading');
    cancelFilePreview();

    const pendingEl = _insertPendingBubble(fileName, blobToSend.size, mimeType, localSrc);

    if (S.ws?.readyState === WebSocket.OPEN) {
        S.ws.send(JSON.stringify({ action: 'file_sending', filename: fileName }));
    }

    try {
        await uploadFileResumable(
            blobToSend,
            fileName,
            S.currentRoom.id,
            csrfToken,
            pct => _updatePendingProgress(pendingEl, pct),
        );
        _finishPendingBubble(pendingEl);
    } catch (err) {
        _failPendingBubble(pendingEl, err.message);
        if (S.ws?.readyState === WebSocket.OPEN) {
            S.ws.send(JSON.stringify({ action: 'stop_file_sending' }));
        }
    }
}

// Глобальная функция для возобновления загрузки
window._resumeUpload = async (uploadId) => {
    // Перечитываем прогресс и продолжаем sendPendingFile
    console.info('[Resumable] Возобновляем загрузку', uploadId);
    if (_pendingFile) await sendPendingFile();
};

// =============================================================================
// Вспомогательные функции предпросмотра (без изменений по сравнению с оригиналом)
// =============================================================================

function _showEditPhotoBtn(show) {
    let btn = $('fpo-edit-photo-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id        = 'fpo-edit-photo-btn';
        btn.className = 'fpo-cancel-btn';
        btn.style.cssText = 'display:none;';
        btn.innerHTML   = '️<div><svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" ><path d="M19.67 2.61c-.81-.81-2.14-.81-2.95 0L3.38 15.95c-.13.13-.22.29-.26.46l-1.09 4.34c-.08.34.01.7.26.95.19.19.45.29.71.29.08 0 .16 0 .24-.03l4.34-1.09c.18-.04.34-.13.46-.26L21.38 7.27c.81-.81.81-2.14 0-2.95L19.66 2.6ZM6.83 19.01l-2.46.61.61-2.46 9.96-9.94 1.84 1.84zM19.98 5.86 18.2 7.64 16.36 5.8l1.78-1.78s.09-.03.12 0l1.72 1.72s.03.09 0 .12"></path></svg></div> <div>Редактировать</div>';
        btn.onclick = () => {
            if (!_pendingFile) return;
            $('file-preview-overlay').classList.remove('show');
            if (typeof window.openPhotoEditor === 'function') {
                window.openPhotoEditor(_pendingFile, (blob, fileName) => {
                    _pendingFile  = new File([blob], fileName, { type: blob.type });
                    _resizedBlob  = null;
                    _skipCompression = false;
                    const reader = new FileReader();
                    reader.onload = ev => {
                        _origDataUrl = ev.target.result;
                        const img = new Image();
                        img.onload = () => {
                            _origW = img.naturalWidth;
                            _origH = img.naturalHeight;
                            $('preview-img').src          = _origDataUrl;
                            $('fpo-filename').textContent = fileName;
                            $('fpo-filesize').textContent = fmtSize(_pendingFile.size);
                            _updateCompressionInfo(parseInt($('compress-slider')?.value || 100));
                        };
                        img.src = _origDataUrl;
                    };
                    reader.readAsDataURL(_pendingFile);
                    $('file-preview-overlay').classList.add('show');
                });
            }
        };
        const actions = document.querySelector('.fpo-actions');
        if (actions) actions.insertBefore(btn, actions.firstChild);
    }
    btn.style.display = show ? '' : 'none';
}

function _showAsFileCard(icon, name, size) {
    $('preview-img').style.display       = 'none';
    $('preview-file-card').style.display = 'flex';
    $('fpo-file-icon').textContent       = icon;
    $('fpo-file-name').textContent       = name;
    $('fpo-file-size').textContent       = fmtSize(size);
    $('fpo-filename').textContent        = name;
    $('fpo-filesize').textContent        = fmtSize(size);
    $('compress-section').style.display  = 'none';
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
    const w = Math.round(_origW * pct / 100);
    const h = Math.round(_origH * pct / 100);
    if ($('compress-dims')) $('compress-dims').textContent = `${w} × ${h}`;
    if ($('compress-pct'))  $('compress-pct').textContent  = pct + '%';
    if (!_pendingFile) return;
    const sizeLabel = $('fpo-filesize');
    if (sizeLabel) {
        sizeLabel.textContent = pct < 100
            ? '~' + fmtSize(Math.round(_pendingFile.size * (pct / 100) * 0.7))
            : fmtSize(_pendingFile.size);
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
    const img = new Image();
    img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = w; canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob(blob => {
            if (!blob) return;
            _resizedBlob = blob;
            $('preview-img').src = URL.createObjectURL(blob);
            if ($('fpo-filesize')) $('fpo-filesize').textContent = fmtSize(blob.size);
        }, _pendingFile.type.includes('png') ? 'image/png' : 'image/jpeg', 0.92);
    };
    img.src = _origDataUrl;
}

export function toggleDotMenu() { $('fpo-dot-menu')?.classList.toggle('show'); }
export function closeDotMenu()  { $('fpo-dot-menu')?.classList.remove('show'); }

export function sendWithoutCompression() {
    _skipCompression = true;
    _resizedBlob     = null;
    const slider = $('compress-slider');
    if (slider) { slider.value = 100; slider.disabled = true; }
    const sec = $('compress-section');
    if (sec) { sec.style.opacity = '0.4'; sec.style.pointerEvents = 'none'; }
    if (_pendingFile) {
        if ($('fpo-filesize')) $('fpo-filesize').textContent = fmtSize(_pendingFile.size);
        if (_origDataUrl && $('preview-img')) $('preview-img').src = _origDataUrl;
    }
    if ($('compress-dims')) $('compress-dims').textContent = `${_origW} × ${_origH}`;
    if ($('compress-pct'))  $('compress-pct').textContent  = '100%';
    const sendBtn = $('fpo-send-btn');
    if (sendBtn) sendBtn.textContent = '↑ Отправить (без сжатия)';
    closeDotMenu();
}

export function cancelFilePreview() {
    if ($('file-preview-overlay')?.classList.contains('uploading')) return;
    _pendingFile = null; _resizedBlob = null; _origDataUrl = null;
    _skipCompression = false; _origW = 0; _origH = 0;

    $('file-preview-overlay').classList.remove('show');
    $('preview-img').src           = '';
    $('preview-img').style.display = 'none';
    $('preview-file-card').style.display = 'none';

    const sec = $('compress-section');
    if (sec) { sec.style.display = 'none'; sec.style.opacity = ''; sec.style.pointerEvents = ''; }
    const slider = $('compress-slider');
    if (slider) slider.disabled = false;
    const errEl = $('fpo-error');
    if (errEl) errEl.style.display = 'none';

    const notice = $('fpo-resume-notice');
    if (notice) notice.style.display = 'none';

    closeDotMenu();
    _resetSendBtn();
    _showEditPhotoBtn(false);
}

export function triggerFileUpload() { $('file-input').click(); }

// =============================================================================
// Обычный XHR upload (для маленьких файлов)
// =============================================================================

function _xhrUpload(url, formData, csrfToken, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url);
        xhr.withCredentials = true;
        xhr.setRequestHeader('X-CSRF-Token', csrfToken);
        xhr.timeout = 120_000;

        xhr.upload.onprogress = e => {
            if (e.lengthComputable) onProgress(Math.round(e.loaded / e.total * 100));
        };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                onProgress(100);
                resolve(JSON.parse(xhr.responseText));
            } else {
                let msg = `HTTP ${xhr.status}`;
                try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
                reject(new Error(msg));
            }
        };
        xhr.onerror   = () => reject(new Error('Нет соединения с сервером'));
        xhr.ontimeout = () => reject(new Error('Таймаут загрузки'));
        xhr.send(formData);
    });
}

// =============================================================================
// Pending bubble — отображение прогресса в чате
// =============================================================================

function _insertPendingBubble(fileName, fileSize, mimeType, localSrc) {
    const S         = window.AppState;
    const isImage   = mimeType.startsWith('image/');
    const container = document.getElementById('messages-container');
    if (!container) return null;

    const wrap = document.createElement('div');
    wrap.className = 'fade-in pending-upload-wrap';

    const user = S?.user;
    const header = document.createElement('div');
    header.className = 'msg-author';
    header.innerHTML = `
        <div class="msg-avatar">${_esc(user?.avatar_emoji || '👤')}</div>
        <span class="msg-name">${_esc(user?.display_name || user?.username || '...')}</span>
        <span class="msg-time">${_fmtNow()}</span>`;
    wrap.appendChild(header);

    if (isImage && localSrc) {
        const bubble = document.createElement('div');
        bubble.className = 'pending-img-bubble';
        bubble.style.backgroundImage = `url(${localSrc})`;
        const badge = document.createElement('div');
        badge.className = 'upload-corner-badge';
        badge.innerHTML = `
            <svg class="ucb-ring" viewBox="0 0 20 20">
                <circle class="ucb-track" cx="10" cy="10" r="7"/>
                <circle class="ucb-fill"  cx="10" cy="10" r="7"/>
            </svg>
            <span class="ucb-pct">0%</span>`;
        bubble.appendChild(badge);
        const meta = document.createElement('div');
        meta.className   = 'pending-img-meta';
        meta.textContent = `${fileName} · ${fmtSize(fileSize)}`;
        bubble.appendChild(meta);
        wrap.appendChild(bubble);
    } else {
        const icon = mimeType.startsWith('video/') ? '🎬'
            : mimeType.startsWith('audio/') ? '🎵'
                : '📄';
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble own file-msg pending-file-bubble';
        bubble.innerHTML = `
            <span class="file-icon">${icon}</span>
            <div class="file-info">
                <div class="file-name">${_esc(fileName)}</div>
                <div class="file-size">${fmtSize(fileSize)}</div>
                <div class="upload-bar-wrap"><div class="upload-bar-fill"></div></div>
                ${fileSize >= RESUMABLE_THRESHOLD ? '<div class="file-size" style="color:#4ecdc4;font-size:10px">⏩ чанковая загрузка</div>' : ''}
            </div>
            <div class="upload-corner-badge" style="position:relative;bottom:auto;right:auto;flex-shrink:0;">
                <svg class="ucb-ring" viewBox="0 0 20 20">
                    <circle class="ucb-track" cx="10" cy="10" r="7"/>
                    <circle class="ucb-fill"  cx="10" cy="10" r="7"/>
                </svg>
                <span class="ucb-pct">0%</span>
            </div>`;
        wrap.appendChild(bubble);
    }

    container.appendChild(wrap);
    container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    return wrap;
}

function _updatePendingProgress(el, pct) {
    if (!el) return;
    const fill  = el.querySelector('.ucb-fill');
    const pctEl = el.querySelector('.ucb-pct');
    if (fill) {
        const circ = 43.98;
        fill.style.strokeDashoffset = `${circ * (1 - pct / 100)}`;
    }
    if (pctEl) pctEl.textContent = pct + '%';
    const barFill = el.querySelector('.upload-bar-fill');
    if (barFill) barFill.style.width = pct + '%';
}

function _finishPendingBubble(el) {
    if (el) el.remove();
}

function _failPendingBubble(el, msg) {
    if (!el) return;
    const badge = el.querySelector('.upload-corner-badge');
    const fill  = el.querySelector('.ucb-fill');
    const pctEl = el.querySelector('.ucb-pct');
    if (badge) badge.classList.add('fail');
    if (fill)  { fill.style.strokeDashoffset = '0'; fill.style.stroke = 'var(--red)'; }
    if (pctEl) pctEl.textContent = '✕';
    const bubble = el.querySelector('.pending-img-bubble, .pending-file-bubble');
    if (bubble) bubble.classList.add('upload-fail');
    const errDiv = document.createElement('div');
    errDiv.className   = 'upload-error-label';
    errDiv.textContent = '⚠ ' + msg;
    el.appendChild(errDiv);
    const retryBtn = document.createElement('button');
    retryBtn.className   = 'upload-retry-btn';
    retryBtn.textContent = '↺ Повторить';
    retryBtn.onclick     = () => { el.remove(); sendPendingFile(); };
    el.appendChild(retryBtn);
}

function _fmtNow() {
    return new Date().toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

function _esc(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _resetSendBtn() {
    const btn = $('fpo-send-btn');
    if (!btn) return;
    btn.disabled         = false;
    btn.style.background = '';
    btn.innerHTML        = '↑ Отправить';
}

function _showError(msg) {
    let el = $('fpo-error');
    if (!el) {
        el = document.createElement('div');
        el.id = 'fpo-error';
        el.style.cssText = 'font-size:12px;color:var(--red);font-family:var(--mono);padding:8px 24px;text-align:center;display:none;';
        $('file-preview-overlay')?.insertBefore(el, $('fpo-bottom-bar'));
    }
    el.textContent   = '⚠ ' + msg;
    el.style.display = 'block';
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.display = 'none'; }, 6000);
}