/**
 * photo-editor.js — Редактор фото перед отправкой
 * Тон, яркость, контраст, насыщенность, поворот, зеркало
 */

let _origImage  = null; // оригинальный File/Blob
let _canvas     = null;
let _ctx        = null;
let _onSave     = null; // callback(blob, fileName)

const DEFAULTS = {
    brightness:  100,
    contrast:    100,
    saturation:  100,
    hue:         0,
    blur:        0,
    rotation:    0,
    flipH:       false,
    flipV:       false,
};

let _state = { ...DEFAULTS };

/**
 * Открыть редактор
 * @param {File|Blob} file  — изображение
 * @param {Function}  onSave — вызывается с (blob, fileName) когда пользователь сохраняет
 */
export function openPhotoEditor(file, onSave) {
    _origImage = file;
    _onSave    = onSave;
    _state     = { ...DEFAULTS };

    _buildEditorUI();
    _loadImage();
}

function _buildEditorUI() {
    document.getElementById('photo-editor-modal')?.remove();

    const modal = document.createElement('div');
    modal.id        = 'photo-editor-modal';
    modal.className = 'photo-editor-modal';

    modal.innerHTML = `
    <div class="photo-editor-inner">
        <div class="photo-editor-header">
            <span class="photo-editor-title">✏️ Редактор фото</span>
            <button class="photo-editor-close" onclick="window.closePhotoEditor()">✕</button>
        </div>

        <div class="photo-editor-body">
            <div class="photo-editor-canvas-wrap">
                <canvas id="photo-ed-canvas"></canvas>
            </div>

            <div class="photo-editor-controls">

                <div class="photo-ed-section">
                    <div class="photo-ed-section-title">🎨 Цвет</div>

                    <label>Яркость <span id="lbl-brightness">100</span>%</label>
                    <input type="range" id="ed-brightness" min="0" max="200" value="100"
                        oninput="window._peUpdate('brightness',+this.value)">

                    <label>Контраст <span id="lbl-contrast">100</span>%</label>
                    <input type="range" id="ed-contrast" min="0" max="200" value="100"
                        oninput="window._peUpdate('contrast',+this.value)">

                    <label>Насыщенность <span id="lbl-saturation">100</span>%</label>
                    <input type="range" id="ed-saturation" min="0" max="300" value="100"
                        oninput="window._peUpdate('saturation',+this.value)">

                    <label>Тон <span id="lbl-hue">0</span>°</label>
                    <input type="range" id="ed-hue" min="0" max="360" value="0"
                        oninput="window._peUpdate('hue',+this.value)">

                    <label>Размытие <span id="lbl-blur">0</span>px</label>
                    <input type="range" id="ed-blur" min="0" max="20" value="0" step="0.5"
                        oninput="window._peUpdate('blur',+this.value)">
                </div>

                <div class="photo-ed-section">
                    <div class="photo-ed-section-title">🔄 Трансформация</div>
                    <div class="photo-ed-btns">
                        <button class="photo-ed-btn" onclick="window._peRotate(-90)" title="Повернуть влево">↺ -90°</button>
                        <button class="photo-ed-btn" onclick="window._peRotate(90)"  title="Повернуть вправо">↻ +90°</button>
                        <button class="photo-ed-btn" onclick="window._peFlip('H')"  title="Зеркало по горизонтали">⇄ Гор.</button>
                        <button class="photo-ed-btn" onclick="window._peFlip('V')"  title="Зеркало по вертикали">⇅ Верт.</button>
                    </div>
                </div>

                <div class="photo-ed-section">
                    <div class="photo-ed-section-title">🎭 Фильтры</div>
                    <div class="photo-ed-filters">
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('none')">Нет</button>
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('grayscale')">Ч/Б</button>
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('sepia')">Сепия</button>
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('vivid')">Яркий</button>
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('cold')">Холодный</button>
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('warm')">Тёплый</button>
                        <button class="photo-ed-filter-btn" onclick="window._peFilter('drama')">Драма</button>
                    </div>
                </div>

                <div class="photo-ed-section">
                    <button class="photo-ed-btn secondary" onclick="window._peReset()">🔄 Сбросить</button>
                </div>
            </div>
        </div>

        <div class="photo-editor-footer">
            <button class="btn btn-secondary" onclick="window.closePhotoEditor()">Отмена</button>
            <button class="btn btn-primary"   onclick="window.savePhotoEdit()">✓ Сохранить и отправить</button>
        </div>
    </div>`;

    document.body.appendChild(modal);
    requestAnimationFrame(() => modal.classList.add('visible'));

    _canvas = document.getElementById('photo-ed-canvas');
    _ctx    = _canvas.getContext('2d');
}

function _loadImage() {
    const url = URL.createObjectURL(_origImage);
    const img = new Image();
    img.onload = () => {
        const MAX = 800;
        let w = img.naturalWidth, h = img.naturalHeight;
        if (w > MAX || h > MAX) {
            if (w > h) { h = Math.round(h * MAX / w); w = MAX; }
            else       { w = Math.round(w * MAX / h); h = MAX; }
        }
        _canvas.width  = w;
        _canvas.height = h;
        _canvas._img   = img;
        _canvas._naturalW = img.naturalWidth;
        _canvas._naturalH = img.naturalHeight;
        URL.revokeObjectURL(url);
        _redraw();
    };
    img.src = url;
}

function _redraw() {
    if (!_canvas?._img) return;
    const img = _canvas._img;
    const s   = _state;
    const w   = _canvas.width, h = _canvas.height;

    _ctx.save();
    _ctx.clearRect(0, 0, w, h);
    _ctx.filter = [
        `brightness(${s.brightness}%)`,
        `contrast(${s.contrast}%)`,
        `saturate(${s.saturation}%)`,
        `hue-rotate(${s.hue}deg)`,
        s.blur > 0 ? `blur(${s.blur}px)` : '',
    ].filter(Boolean).join(' ');
    _ctx.translate(w / 2, h / 2);
    _ctx.rotate((s.rotation * Math.PI) / 180);
    _ctx.scale(s.flipH ? -1 : 1, s.flipV ? -1 : 1);

    const isRot = s.rotation % 180 !== 0;
    const dw    = isRot ? h : w;
    const dh    = isRot ? w : h;
    _ctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
    _ctx.restore();
}

window._peUpdate = (key, val) => {
    _state[key] = val;
    const lbl = document.getElementById(`lbl-${key}`);
    if (lbl) lbl.textContent = Math.round(val);
    _redraw();
};

window._peRotate = (deg) => {
    _state.rotation = (_state.rotation + deg + 360) % 360;
    _redraw();
};

window._peFlip = (axis) => {
    if (axis === 'H') _state.flipH = !_state.flipH;
    else               _state.flipV = !_state.flipV;
    _redraw();
};

window._peFilter = (name) => {
    document.querySelectorAll('.photo-ed-filter-btn').forEach(b => b.classList.remove('active'));
    event?.target?.classList.add('active');

    switch (name) {
        case 'none':
            _state.brightness = 100; _state.contrast = 100;
            _state.saturation = 100; _state.hue = 0; _state.blur = 0;
            break;
        case 'grayscale':
            _state.saturation = 0; _state.brightness = 100; _state.contrast = 110;
            break;
        case 'sepia':
            _state.saturation = 30; _state.brightness = 105;
            _state.hue = 20; _state.contrast = 90;
            break;
        case 'vivid':
            _state.saturation = 180; _state.brightness = 110;
            _state.contrast = 120; _state.hue = 0;
            break;
        case 'cold':
            _state.saturation = 90; _state.brightness = 100;
            _state.hue = 200; _state.contrast = 105;
            break;
        case 'warm':
            _state.saturation = 110; _state.brightness = 105;
            _state.hue = 15; _state.contrast = 100;
            break;
        case 'drama':
            _state.saturation = 120; _state.brightness = 90;
            _state.contrast = 150; _state.hue = 0; _state.blur = 0;
            break;
    }

    ['brightness','contrast','saturation','hue','blur'].forEach(k => {
        const el = document.getElementById(`ed-${k}`);
        if (el) el.value = _state[k];
        const lb = document.getElementById(`lbl-${k}`);
        if (lb) lb.textContent = Math.round(_state[k]);
    });
    _redraw();
};

window._peReset = () => {
    _state = { ...DEFAULTS };
    ['brightness','contrast','saturation','hue','blur'].forEach(k => {
        const el = document.getElementById(`ed-${k}`);
        if (el) el.value = DEFAULTS[k];
        const lb = document.getElementById(`lbl-${k}`);
        if (lb) lb.textContent = Math.round(DEFAULTS[k]);
    });
    _redraw();
};

window.closePhotoEditor = () => {
    document.getElementById('photo-editor-modal')?.remove();
    _origImage = null; _onSave = null;
};

window.savePhotoEdit = () => {
    if (!_canvas) return;
    const offscreen = document.createElement('canvas');
    const ox = _canvas._naturalW || _canvas.width;
    const oy = _canvas._naturalH || _canvas.height;
    const s  = _state;

    offscreen.width  = ox;
    offscreen.height = oy;
    const oc = offscreen.getContext('2d');

    oc.filter = [
        `brightness(${s.brightness}%)`,
        `contrast(${s.contrast}%)`,
        `saturate(${s.saturation}%)`,
        `hue-rotate(${s.hue}deg)`,
        s.blur > 0 ? `blur(${s.blur}px)` : '',
    ].filter(Boolean).join(' ');

    oc.save();
    oc.translate(ox / 2, oy / 2);
    oc.rotate((s.rotation * Math.PI) / 180);
    oc.scale(s.flipH ? -1 : 1, s.flipV ? -1 : 1);
    const isRot = s.rotation % 180 !== 0;
    const dw    = isRot ? oy : ox;
    const dh    = isRot ? ox : oy;
    oc.drawImage(_canvas._img, -dw / 2, -dh / 2, dw, dh);
    oc.restore();

    offscreen.toBlob(blob => {
        const origName = _origImage?.name || 'photo.jpg';
        const ext      = origName.split('.').pop() || 'jpg';
        const newName  = origName.replace(/\.[^.]+$/, '') + '_edited.' + ext;

        if (_onSave) _onSave(blob, newName);
        window.closePhotoEditor();
    }, 'image/jpeg', 0.92);
};