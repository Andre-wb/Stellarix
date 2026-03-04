// static/js/chat/file-upload.js
// =============================================================================
// Модуль загрузки файлов в чат.
// Управляет предпросмотром, сжатием изображений, отправкой через XHR,
// отображением прогресса и обработкой ошибок.
// =============================================================================

import { fmtSize, getCookie } from '../utils.js';

// Приватные переменные состояния загружаемого файла
let _pendingFile     = null;      // Исходный File объект
let _resizedBlob     = null;      // Сжатый blob (если применимо)
let _origW           = 0;         // Оригинальная ширина изображения
let _origH           = 0;         // Оригинальная высота
let _origDataUrl     = null;      // data:URL оригинального изображения (для предпросмотра)
let _skipCompression = false;     // true если пользователь выбрал "без сжатия"

// Короткая функция для получения элемента по id
const $ = id => document.getElementById(id);

/**
 * Обработчик выбора файла через <input type="file">.
 * Сохраняет файл в _pendingFile, показывает оверлей предпросмотра.
 * Для изображений дополнительно загружает превью, определяет размеры,
 * показывает слайдер сжатия и кнопку редактора.
 * Для остальных файлов показывает карточку с иконкой.
 *
 * @param {Event} e - событие change input
 */
export function uploadFile(e) {
    const file = e.target.files[0];
    e.target.value = ''; // сбрасываем input, чтобы можно было выбрать тот же файл повторно
    if (!file) return;

    // Сброс состояния
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

    const isImage = file.type.startsWith('image/');

    if (isImage) {
        // Прячем карточку файла, показываем область для изображения
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
                _showEditPhotoBtn(true);       // показываем кнопку «Редактировать»
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

/**
 * Показывает или скрывает кнопку «Редактировать фото».
 * Если кнопка ещё не создана, создаёт её и вставляет в .fpo-actions.
 *
 * @param {boolean} show - true показать, false скрыть
 */
function _showEditPhotoBtn(show) {
    let btn = $('fpo-edit-photo-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id        = 'fpo-edit-photo-btn';
        btn.className = 'fpo-cancel-btn';
        btn.style.cssText = 'display:none;';
        btn.textContent   = '✏️ Редактировать';
        btn.onclick = () => {
            if (!_pendingFile) return;
            $('file-preview-overlay').classList.remove('show');
            // Вызываем глобальный редактор фото (определён в другом месте)
            if (typeof window.openPhotoEditor === 'function') {
                window.openPhotoEditor(_pendingFile, (blob, fileName) => {
                    // Заменяем ожидающий файл отредактированным
                    _pendingFile  = new File([blob], fileName, { type: blob.type });
                    _resizedBlob  = null;
                    _skipCompression = false;
                    // Перечитываем превью
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
        // Вставляем перед кнопкой «Отмена» в нижней панели
        const actions = document.querySelector('.fpo-actions');
        if (actions) actions.insertBefore(btn, actions.firstChild);
    }
    btn.style.display = show ? '' : 'none';
}

/**
 * Показывает предпросмотр в виде карточки (иконка + имя + размер) для не-изображений.
 *
 * @param {string} icon - эмодзи-иконка (🖼, 🎬, 🎵, 📄)
 * @param {string} name - имя файла
 * @param {number} size - размер в байтах
 */
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

/**
 * Показывает секцию сжатия (слайдер) и устанавливает значение.
 *
 * @param {number} pct - начальный процент сжатия (обычно 100)
 */
function _showCompressionSection(pct) {
    const sec = $('compress-section');
    if (!sec) return;
    sec.style.display = 'block';
    const slider = $('compress-slider');
    if (slider) slider.value = pct;
}

/**
 * Обработчик изменения слайдера сжатия.
 * Вызывается из HTML (oninput).
 * @param {string|number} val - текущее значение слайдера (0‑100)
 */
export function onCompressSlider(val) {
    if (_skipCompression) return; // если выбрано «без сжатия», игнорируем
    const pct = parseInt(val, 10);
    _updateCompressionInfo(pct);
    _applyCompression(pct);
}

/**
 * Обновляет текстовую информацию о сжатии (размеры, итоговый размер файла).
 *
 * @param {number} pct - процент от оригинала
 */
function _updateCompressionInfo(pct) {
    const w = Math.round(_origW * pct / 100);
    const h = Math.round(_origH * pct / 100);
    if ($('compress-dims')) $('compress-dims').textContent = `${w} × ${h}`;
    if ($('compress-pct'))  $('compress-pct').textContent  = pct + '%';
    if (!_pendingFile) return;
    const sizeLabel = $('fpo-filesize');
    if (sizeLabel) {
        sizeLabel.textContent = pct < 100
            ? '~' + fmtSize(Math.round(_pendingFile.size * (pct / 100) * 0.7)) // эмпирический коэффициент 0.7
            : fmtSize(_pendingFile.size);
    }
}

/**
 * Применяет сжатие изображения: создаёт canvas, ресайзит, конвертирует в blob.
 * Обновляет preview и _resizedBlob.
 *
 * @param {number} pct - процент от оригинала
 */
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

/**
 * Переключает отображение меню с точками (три точки) в предпросмотре.
 */
export function toggleDotMenu() {
    $('fpo-dot-menu')?.classList.toggle('show');
}

/**
 * Закрывает меню с точками.
 */
export function closeDotMenu() {
    $('fpo-dot-menu')?.classList.remove('show');
}

/**
 * Обработчик пункта «Отправить без сжатия».
 * Устанавливает _skipCompression = true, блокирует слайдер, меняет текст кнопки.
 */
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

/**
 * Отменяет предпросмотр файла (закрывает оверлей, сбрасывает состояние).
 */
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
    closeDotMenu();
    _resetSendBtn();
    _showEditPhotoBtn(false);
}

/**
 * Отправляет ожидающий файл на сервер.
 * Использует FormData и XHR с отслеживанием прогресса.
 * При успехе удаляет временный pending-элемент, при ошибке показывает кнопку повтора.
 */
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
    cancelFilePreview(); // закрываем оверлей предпросмотра

    const pendingEl = _insertPendingBubble(fileName, blobToSend.size, mimeType, localSrc);
    const formData = new FormData();
    formData.append('file', new File([blobToSend], fileName, { type: mimeType }));

    if (S.ws?.readyState === WebSocket.OPEN) {
        S.ws.send(JSON.stringify({ action: 'file_sending', filename: fileName }));
    }

    try {
        await _xhrUpload(
            `/api/files/upload/${S.currentRoom.id}`,
            formData,
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

/**
 * Программно открывает диалог выбора файла.
 */
export function triggerFileUpload() {
    $('file-input').click();
}

/**
 * Внутренняя функция XHR-загрузки с прогрессом.
 *
 * @param {string} url
 * @param {FormData} formData
 * @param {string} csrfToken
 * @param {function(number)} onProgress - колбэк с процентом (0‑100)
 * @returns {Promise<any>} - ответ сервера (распарсенный JSON)
 */
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
                try { msg = JSON.parse(xhr.responseText).detail || JSON.parse(xhr.responseText).error || msg; } catch {}
                reject(new Error(msg));
            }
        };
        xhr.onerror   = () => reject(new Error('Нет соединения с сервером'));
        xhr.ontimeout = () => reject(new Error('Таймаут загрузки'));
        xhr.send(formData);
    });
}

/**
 * Вставляет временный элемент сообщения (pending bubble) в список сообщений,
 * пока файл загружается. Для изображений отображает миниатюру.
 *
 * @param {string} fileName
 * @param {number} fileSize
 * @param {string} mimeType
 * @param {string|null} localSrc - data:URL для предпросмотра изображения
 * @returns {HTMLElement} - обёртка, в которой будет обновляться прогресс
 */
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

/**
 * Обновляет процент загрузки в pending-элементе (круговой индикатор и/или полоска).
 *
 * @param {HTMLElement} el - элемент-обёртка
 * @param {number} pct - процент (0‑100)
 */
function _updatePendingProgress(el, pct) {
    if (!el) return;
    const fill  = el.querySelector('.ucb-fill');
    const pctEl = el.querySelector('.ucb-pct');
    if (fill) {
        const circ = 43.98; // длина окружности для r=7 (2*pi*7 ≈ 43.98)
        fill.style.strokeDashoffset = `${circ * (1 - pct / 100)}`;
    }
    if (pctEl) pctEl.textContent = pct + '%';
    const barFill = el.querySelector('.upload-bar-fill');
    if (barFill) barFill.style.width = pct + '%';
}

/**
 * Удаляет pending-элемент после успешной загрузки.
 *
 * @param {HTMLElement} el
 */
function _finishPendingBubble(el) {
    if (!el) return;
    el.remove();
}

/**
 * Отображает ошибку загрузки в pending-элементе, добавляет кнопку повтора.
 *
 * @param {HTMLElement} el
 * @param {string} msg - текст ошибки
 */
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

/**
 * Возвращает текущее время в формате ЧЧ:ММ.
 */
function _fmtNow() {
    return new Date().toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Экранирует HTML-спецсимволы в строке.
 */
function _esc(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/**
 * Сбрасывает кнопку отправки в исходное состояние (после отмены или ошибки).
 */
function _resetSendBtn() {
    const btn = $('fpo-send-btn');
    if (!btn) return;
    btn.disabled         = false;
    btn.style.background = '';
    btn.innerHTML        = '↑ Отправить';
}

/**
 * Показывает сообщение об ошибке в оверлее предпросмотра.
 *
 * @param {string} msg
 */
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