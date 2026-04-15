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
import { encryptFile, decryptFile, getRoomKey, setRoomKey } from '../crypto.js';
import { encryptFileMeta, isZKReady } from '../zk-crypto.js';


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
let _customVideoThumb = null; // data URL of custom thumbnail
let _currentXhr      = null;  // for abort

function _abortUpload() {
    if (_currentXhr) { try { _currentXhr.abort(); } catch(_) {} _currentXhr = null; }
    _sendingInProgress = false;
}

/**
 * Extract thumbnail from video file — grabs frame at 0.5s (or 0s if shorter).
 * Returns data URL (JPEG). Fast: uses offscreen video + canvas, no full decode needed.
 */
function _extractVideoThumbnail(fileOrBlob, seekTime = 0.5) {
    return new Promise((resolve, reject) => {
        const video = document.createElement('video');
        video.preload = 'metadata';
        video.muted = true;
        video.playsInline = true;
        const objUrl = URL.createObjectURL(fileOrBlob);
        video.src = objUrl;

        const cleanup = () => { URL.revokeObjectURL(objUrl); };
        const timeout = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, 5000);

        video.addEventListener('loadedmetadata', () => {
            // Seek to 0.5s or 0 if video is shorter
            video.currentTime = Math.min(seekTime, video.duration || 0);
        }, { once: true });

        video.addEventListener('seeked', () => {
            clearTimeout(timeout);
            try {
                const canvas = document.createElement('canvas');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
                cleanup();
                resolve(dataUrl);
            } catch (e) {
                cleanup();
                reject(e);
            }
        }, { once: true });

        video.addEventListener('error', () => { clearTimeout(timeout); cleanup(); reject(new Error('video error')); }, { once: true });
    });
}

// Video thumbnail tools removed — replaced by full video editor (video-editor.js)

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
async function uploadFileResumable(fileOrBlob, fileName, roomId, csrfToken, onProgress, captionCt) {
    const fileSize = fileOrBlob.size;

    if (fileSize < RESUMABLE_THRESHOLD) {
        // Маленький файл — обычная загрузка (уже зашифрован на вызывающей стороне)
        const formData = new FormData();
        let blob = fileOrBlob;
        formData.append('file', new File([blob], fileName, { type: blob.type }));
        if (captionCt) formData.append('caption_ct', captionCt);
        // ZK: шифруем имя файла room key, чтобы сервер не видел plaintext
        if (isZKReady()) {
            try {
                const encMeta = await encryptFileMeta(roomId, { file_name: fileName });
                if (encMeta.file_name_encrypted) {
                    formData.append('file_name_encrypted', encMeta.file_name_encrypted);
                }
            } catch (e) { console.warn('[ZK] file_name encryption skipped:', e.message); }
        }
        return _xhrUpload(`/api/files/upload/${roomId}`, formData, csrfToken, onProgress);
    }

    // ── Крупный файл — чанкованная загрузка ───────────────────────────────────
    // File already encrypted by caller — just chunk it
    let fileBuffer = await fileOrBlob.arrayBuffer();
    const fileHash = await sha256Hex(fileBuffer);
    const encFileSize = fileBuffer.byteLength; // may differ from original after encryption

    const totalChunks = Math.ceil(encFileSize / CHUNK_SIZE);

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
        initForm.append('file_size', encFileSize);
        initForm.append('file_hash', fileHash);
        initForm.append('chunk_size', CHUNK_SIZE);

        const initResp = await fetch('/api/files/upload-init', {
            method:      'POST',
            body:        initForm,
            credentials: 'include',
            headers:     { 'X-CSRF-Token': csrfToken },
        });
        if (!initResp.ok) {
            throw new Error(t('upload.initError', {status: initResp.status}));
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
        const end      = Math.min(start + CHUNK_SIZE, encFileSize);
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
        throw new Error(t('upload.chunkFailed', {chunk: chunkIdx, retries: CHUNK_RETRY_MAX}));
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
        throw new Error(errData.error || errData.detail || t('upload.assemblyError', {status: completeResp.status}));
    }

    _clearProgress(uploadId);
    _resumeSession = null;
    onProgress(100);

    return await completeResp.json();
}

// =============================================================================
// Обработчик выбора файла
// =============================================================================

export async function uploadFile(e) {
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
        if (label) label.textContent = fmtSize(file.size) + ' · ' + t('file.chunkedUpload');
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
        reader.onerror = () => _showAsFileCard('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>', file.name, file.size);
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
            img.onerror = () => _showAsFileCard('<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>', file.name, file.size);
            img.src = _origDataUrl;
        };
        reader.readAsDataURL(file);
    } else if (file.type.startsWith('video/')) {
        // Open full video editor
        const { openVideoEditor } = await import('./video-editor.js');
        openVideoEditor(file, async (result) => {
            _pendingFile = result.file;
            _customVideoThumb = result.thumbnail || null;
            if (result.muted) _pendingFile._muted = true;
            // Save thumbnail and timecodes to sessionStorage for render.js and player
            if (_customVideoThumb) {
                try { sessionStorage.setItem('vortex_vthumb_' + _pendingFile.name, _customVideoThumb); } catch(_) {}
            }
            if (result.timecodes?.length) {
                try { sessionStorage.setItem('vortex_vtc_' + _pendingFile.name, JSON.stringify(result.timecodes)); } catch(_) {}
            }
            await sendPendingFile();
        }, () => {
            // cancelled
            _pendingFile = null;
        });
    } else {
        const isAudio = file.type.startsWith('audio/');
        const iconSvg = isAudio
            ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>'
            : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>';
        _showAsFileCard(iconSvg, file.name, file.size);
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
        t('upload.resumeNotice') + ' ' +
        `<button onclick="window._resumeUpload && window._resumeUpload('${uploadId}')" ` +
        `style="background:none;border:none;color:#4ecdc4;cursor:pointer;text-decoration:underline;padding:0">${t('upload.resume')}</button>`;
    notice.style.display = 'flex';
}

// =============================================================================
// Отправка файла
// =============================================================================

let _sendingInProgress = false;
export async function sendPendingFile() {
    if (!_pendingFile || _sendingInProgress) return;
    _sendingInProgress = true;
    const S = window.AppState;
    if (!S?.currentRoom?.id) { _sendingInProgress = false; return; }

    const csrfToken = S.csrfToken || getCookie('csrf_token');
    if (!csrfToken) { _showError(t('upload.csrfNotFound')); return; }

    let blobToSend = (_resizedBlob && !_skipCompression) ? _resizedBlob : _pendingFile;
    const fileName   = _pendingFile.name;
    const mimeType   = _pendingFile.type;
    const localSrc   = _origDataUrl || null;

    // Generate video thumbnail before encryption (first frame at 0.5s or 0s)
    let videoThumb = localSrc; // fallback for images
    if (mimeType.startsWith('video/')) {
        // Use custom thumbnail from editor, or extract automatically
        if (_customVideoThumb) {
            videoThumb = _customVideoThumb;
        } else if (!localSrc) {
            try { videoThumb = await _extractVideoThumbnail(blobToSend); } catch (_) {}
        }
    }

    // E2E: шифруем содержимое файла ключом комнаты перед отправкой
    let roomKey = getRoomKey(S.currentRoom.id);
    if (!roomKey) {
        // Generate key if missing — MUST encrypt all files
        roomKey = crypto.getRandomValues(new Uint8Array(32));
        setRoomKey(S.currentRoom.id, roomKey);
        console.warn('[E2E] Generated room key for room', S.currentRoom.id);
    }
    try {
        const fileBuffer = await blobToSend.arrayBuffer();
        const encryptedBuffer = await encryptFile(fileBuffer, roomKey);
        blobToSend = new File([encryptedBuffer], fileName, { type: 'application/octet-stream' });
    } catch (e) {
        console.error('[E2E] File encryption failed:', e);
    }

    // Grab caption before closing preview
    const captionEl = $('fpo-caption');
    const caption = (captionEl?.value || '').trim();

    $('file-preview-overlay')?.classList.remove('uploading');
    cancelFilePreview();

    const pendingEl = _insertPendingBubble(fileName, blobToSend.size, mimeType, videoThumb || localSrc);

    // Save video thumbnail for render.js to use as poster
    if (mimeType.startsWith('video/') && videoThumb) {
        try { sessionStorage.setItem('vortex_vthumb_' + fileName, videoThumb); } catch(_) {}
    }

    if (S.ws?.readyState === WebSocket.OPEN) {
        S.ws.send(JSON.stringify({ action: 'file_sending', filename: fileName }));
    }

    // Encrypt caption if present
    let captionCt = null;
    if (caption) {
        try {
            const { ratchetEncrypt } = await import('../crypto.js');
            captionCt = await ratchetEncrypt(caption, S.currentRoom.id, S.user.id, roomKey);
        } catch {
            try {
                const { encryptText } = await import('../crypto.js');
                captionCt = await encryptText(caption, roomKey);
            } catch {}
        }
    }

    try {
        await uploadFileResumable(
            blobToSend,
            fileName,
            S.currentRoom.id,
            csrfToken,
            pct => _updatePendingProgress(pendingEl, pct),
            captionCt,
        );
        _finishPendingBubble(pendingEl);
    } catch (err) {
        _failPendingBubble(pendingEl, err.message);
    } finally {
        _sendingInProgress = false;
        if (S.ws?.readyState === WebSocket.OPEN) {
            try { S.ws.send(JSON.stringify({ action: 'stop_file_sending' })); } catch {}
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
        btn.innerHTML   = '️<div><svg  xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24" ><path d="M19.67 2.61c-.81-.81-2.14-.81-2.95 0L3.38 15.95c-.13.13-.22.29-.26.46l-1.09 4.34c-.08.34.01.7.26.95.19.19.45.29.71.29.08 0 .16 0 .24-.03l4.34-1.09c.18-.04.34-.13.46-.26L21.38 7.27c.81-.81.81-2.14 0-2.95L19.66 2.6ZM6.83 19.01l-2.46.61.61-2.46 9.96-9.94 1.84 1.84zM19.98 5.86 18.2 7.64 16.36 5.8l1.78-1.78s.09-.03.12 0l1.72 1.72s.03.09 0 .12"></path></svg></div> <div>' + t('upload.editPhoto') + '</div>';
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
    $('fpo-file-icon').innerHTML          = icon;
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
    if (sendBtn) sendBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' + t('file.sendOriginal');
    closeDotMenu();
}

export function cancelFilePreview() {
    if ($('file-preview-overlay')?.classList.contains('uploading')) return;
    _pendingFile = null; _resizedBlob = null; _origDataUrl = null;
    _skipCompression = false; _origW = 0; _origH = 0;
    const captionEl = $('fpo-caption');
    if (captionEl) captionEl.value = '';

    $('file-preview-overlay').classList.remove('show');
    $('preview-img').src           = '';
    $('preview-img').style.display = 'none';
    // Stop video preview and cleanup thumbnail tools
    const videoEl = document.getElementById('preview-video');
    if (videoEl) { videoEl.pause(); videoEl.src = ''; videoEl.style.display = 'none'; }
    document.getElementById('video-thumb-tools')?.remove();
    _customVideoThumb = null;
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

/**
 * Принимает File из Drag & Drop и запускает тот же flow, что и uploadFile.
 * Создаёт фиктивный объект-событие для совместимости.
 * @param {File} file
 */
export function uploadFileFromDrop(file) {
    if (!file) return;
    // Создаём минимальную обёртку, имитирующую e.target.files[0]
    const fakeEvent = { target: { files: [file], value: '' } };
    // Подавляем сброс input.value, т.к. target — обычный объект
    uploadFile(fakeEvent);
}

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
        _currentXhr = xhr;

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
        xhr.onerror   = () => reject(new Error(t('file.noConnection')));
        xhr.ontimeout = () => reject(new Error(t('file.uploadTimeout')));
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
    var avatarContent = user?.avatar_url
        ? '<img src="' + _esc(user.avatar_url) + '" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">'
        : (user?.avatar_emoji ? _esc(user.avatar_emoji) : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>');
    header.innerHTML = `
        <div class="msg-avatar">${avatarContent}</div>
        <span class="msg-name">${_esc(user?.display_name || user?.username || '...')}</span>
        <span class="msg-time">${_fmtNow()}</span>`;
    wrap.appendChild(header);

    const isVideo = mimeType.startsWith('video/');
    if ((isImage || isVideo) && localSrc) {
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
        // Cancel button
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'upload-cancel-btn';
        cancelBtn.style.cssText = 'position:absolute;top:6px;right:6px;z-index:3;background:rgba(0,0,0,.6);';
        cancelBtn.title = 'Cancel';
        cancelBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        cancelBtn.addEventListener('click', () => { _abortUpload(); wrap.remove(); });
        bubble.appendChild(cancelBtn);
        if (isVideo) {
            const playIcon = document.createElement('div');
            playIcon.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;';
            playIcon.innerHTML = '<svg width="40" height="40" viewBox="0 0 24 24" fill="white" opacity="0.7"><path d="M8 5v14l11-7z"/></svg>';
            bubble.appendChild(playIcon);
        }
        const meta = document.createElement('div');
        meta.className   = 'pending-img-meta';
        meta.textContent = `${fileName} · ${fmtSize(fileSize)}`;
        bubble.appendChild(meta);
        wrap.appendChild(bubble);
    } else {
        const icon = mimeType.startsWith('video/')
            ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z"/></svg>'
            : mimeType.startsWith('audio/')
                ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>'
                : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>';
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble own file-msg pending-file-bubble';
        bubble.innerHTML = `
            <span class="file-icon">${icon}</span>
            <div class="file-info">
                <div class="file-name">${_esc(fileName)}</div>
                <div class="file-size">${fmtSize(fileSize)}</div>
                <div class="upload-bar-wrap"><div class="upload-bar-fill"></div></div>
            </div>
            <div class="upload-corner-badge" style="position:relative;bottom:auto;right:auto;flex-shrink:0;">
                <svg class="ucb-ring" viewBox="0 0 20 20">
                    <circle class="ucb-track" cx="10" cy="10" r="7"/>
                    <circle class="ucb-fill"  cx="10" cy="10" r="7"/>
                </svg>
                <span class="ucb-pct">0%</span>
            </div>`;
        // Add cancel button (safe DOM)
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'upload-cancel-btn';
        cancelBtn.title = 'Cancel';
        cancelBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        cancelBtn.addEventListener('click', () => { _abortUpload(); wrap.remove(); });
        bubble.appendChild(cancelBtn);
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
    const cancelBtn = el.querySelector('.upload-cancel-btn');
    if (badge) badge.classList.add('fail');
    if (fill)  { fill.style.strokeDashoffset = '0'; fill.style.stroke = 'var(--red)'; }
    if (pctEl) pctEl.textContent = '!';
    if (cancelBtn) cancelBtn.remove();
    const bubble = el.querySelector('.pending-img-bubble, .pending-file-bubble');
    if (bubble) bubble.classList.add('upload-fail');
    // Error + retry inside bubble
    const errWrap = document.createElement('div');
    errWrap.style.cssText = 'width:100%;padding:6px 0 0;';
    const errDiv = document.createElement('div');
    errDiv.className = 'upload-error-label';
    errDiv.textContent = msg;
    errWrap.appendChild(errDiv);
    const retryBtn = document.createElement('button');
    retryBtn.className = 'upload-retry-btn';
    retryBtn.textContent = 'Retry';
    retryBtn.addEventListener('click', () => { el.remove(); sendPendingFile(); });
    errWrap.appendChild(retryBtn);
    if (bubble) bubble.appendChild(errWrap);
    else el.appendChild(errWrap);
}

function _fmtNow() {
    return new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
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
    btn.innerHTML        = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' + t('chat.send');
}

function _showError(msg) {
    let el = $('fpo-error');
    if (!el) {
        el = document.createElement('div');
        el.id = 'fpo-error';
        el.style.cssText = 'font-size:12px;color:var(--red);font-family:var(--mono);padding:8px 24px;text-align:center;display:none;';
        $('file-preview-overlay')?.insertBefore(el, $('fpo-bottom-bar'));
    }
    el.textContent   = msg;
    el.style.display = 'block';
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.display = 'none'; }, 6000);
}

// =============================================================================
// E2E: скачивание и расшифровка файлов
// =============================================================================

/**
 * Скачивает файл, расшифровывает ключом комнаты и отдаёт пользователю.
 * Для legacy (незашифрованных) файлов — просто скачивает как есть.
 *
 * @param {string} downloadUrl — URL для скачивания файла
 * @param {string} fileName — имя файла для сохранения
 */
export async function downloadAndDecryptFile(downloadUrl, fileName) {
    const roomKey = getRoomKey(window.AppState?.currentRoom?.id);

    try {
        const resp = await fetch(downloadUrl, { credentials: 'include' });
        if (!resp.ok) throw new Error('Download failed: HTTP ' + resp.status);

        let fileData = await resp.arrayBuffer();

        // Пытаемся расшифровать (если есть ключ и данные достаточной длины)
        if (roomKey && fileData.byteLength > 12) {
            try {
                fileData = await decryptFile(fileData, roomKey);
            } catch {
                // Файл может быть незашифрованным (legacy) — используем как есть
                console.warn('[E2E] Расшифровка файла не удалась — возможно, legacy (незашифрованный)');
            }
        }

        // Создаём blob и запускаем скачивание
        const blob = new Blob([fileData]);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName || 'file';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        console.error('[E2E] Ошибка загрузки файла:', e);
        alert(t('file.downloadError') + ': ' + e.message);
    }
}

/**
 * Загружает зашифрованное изображение, расшифровывает и устанавливает blob URL.
 * Используется для inline-изображений в сообщениях.
 *
 * @param {HTMLImageElement} imgEl — элемент img
 * @param {string} url — URL зашифрованного изображения
 */
// Cache decrypted blob URLs to avoid re-downloading
const _blobCache = {};

export async function loadEncryptedMedia(el, url, mimeHint) {
    // Return cached blob URL if available
    if (_blobCache[url]) {
        el.src = _blobCache[url];
        return _blobCache[url];
    }
    const roomKey = getRoomKey(window.AppState?.currentRoom?.id);
    try {
        const resp = await fetch(url, { credentials: 'include' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        let data = await resp.arrayBuffer();
        if (roomKey && data.byteLength > 28) {
            try { data = await decryptFile(data, roomKey); } catch { /* legacy */ }
        }
        const blob = new Blob([data], mimeHint ? { type: mimeHint } : undefined);
        const blobUrl = URL.createObjectURL(blob);
        _blobCache[url] = blobUrl;
        el.src = blobUrl;
        return blobUrl;
    } catch (e) {
        console.warn('[E2E] Media load failed:', url, e);
        if (el.tagName === 'IMG') el.alt = '[load failed]';
    }
}

// Backward-compatible alias
export async function loadEncryptedImage(imgEl, url) {
    return loadEncryptedMedia(imgEl, url);
}