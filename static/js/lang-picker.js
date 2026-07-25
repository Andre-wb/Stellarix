const _LP_LANGS = [
    {code:"ru",name:"Русский",hint:"Выберите язык"},
    {code:"en",name:"English",hint:"Choose your language"},
];

let _lpSelected = null;

const _TITLE_HINTS = _LP_LANGS.map(l => l.hint).filter(Boolean);

let _titleIdx = 0;
let _titleRunning = false;

const _TYPE_SPEED = 45;
const _DELETE_SPEED = 30;
const _PAUSE_AFTER = 1800;

function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function _typewriterLoop() {
    const el = document.getElementById('lp-title');
    if (!el) return;
    _titleRunning = true;

    while (_titleRunning) {
        const text = _TITLE_HINTS[_titleIdx];

        for (let i = 0; i <= text.length && _titleRunning; i++) {
            el.textContent = text.slice(0, i);
            await _sleep(_TYPE_SPEED);
        }

        if (!_titleRunning) break;
        await _sleep(_PAUSE_AFTER);
        if (!_titleRunning) break;

        const current = el.textContent;
        for (let i = current.length; i >= 0 && _titleRunning; i--) {
            el.textContent = current.slice(0, i);
            await _sleep(_DELETE_SPEED);
        }

        if (!_titleRunning) break;
        await _sleep(200);

        _titleIdx = (_titleIdx + 1) % _TITLE_HINTS.length;
    }
}

function _startTitleRotation() {
    _titleRunning = true;
    _typewriterLoop();
}

function _stopTitleRotation() {
    _titleRunning = false;
}

function _createLpItem(lang) {
    const div = document.createElement('div');
    div.className = 'lp-item' + (_lpSelected === lang.code ? ' selected' : '');
    div.dataset.code = lang.code;
    div.onclick = () => window._lpSelect(lang.code);

    const radio = document.createElement('div');
    radio.className = 'lp-item-radio';

    const name = document.createElement('span');
    name.className = 'lp-item-name';
    name.textContent = lang.name;

    const code = document.createElement('span');
    code.className = 'lp-item-code';
    code.textContent = lang.code;

    div.append(radio, name, code);
    return div;
}

function _renderLpList() {
    const list = document.getElementById('lp-list');
    if (!list) return;
    list.replaceChildren(..._LP_LANGS.map(_createLpItem));
}

let _selectVersion = 0;

window._lpSelect = function(code) {
    _lpSelected = code;
    _renderLpList();

    const btn = document.getElementById('lp-continue');
    if (btn) btn.disabled = false;

    const lang = _LP_LANGS.find(l => l.code === code);
    if (lang) {
        _stopTitleRotation();
        const el = document.getElementById('lp-title');
        if (el) {
            const ver = ++_selectVersion;
            const oldText = el.textContent;
            (async () => {
                for (let i = oldText.length; i >= 0; i--) {
                    if (_selectVersion !== ver) return;
                    el.textContent = oldText.slice(0, i);
                    await _sleep(_DELETE_SPEED);
                }
                if (_selectVersion !== ver) return;
                await _sleep(150);
                const newText = lang.hint;
                for (let i = 0; i <= newText.length; i++) {
                    if (_selectVersion !== ver) return;
                    el.textContent = newText.slice(0, i);
                    await _sleep(_TYPE_SPEED);
                }
            })();
        }

        const CONTINUE_MAP = { ru:"Продолжить", en:"Continue" };
        const btnText = document.getElementById('lp-continue-text');
        if (btnText) btnText.textContent = CONTINUE_MAP[code] || 'Continue';

        const SUB_MAP = {
            ru:"Можно изменить позже в настройках",
            en:"You can change it later in settings",
        };
        const sub = document.getElementById('lp-subtitle');
        if (sub) sub.textContent = SUB_MAP[code] || SUB_MAP.en;
    }
};

window._lpConfirm = function() {
    if (!_lpSelected) return;

    if (typeof StxI18n !== 'undefined') StxI18n.set(_lpSelected);

    const screen = document.getElementById('lang-picker-screen');
    if (screen) {
        screen.style.transition = 'opacity 0.4s ease-out';
        screen.style.opacity = '0';
        setTimeout(() => {
            screen.style.display = 'none';
        }, 400);
    }

    _stopTitleRotation();
};

function initLangPicker() {
    let saved = null;
    try { saved = localStorage.getItem('stx_lang'); } catch (e) {}
    if (saved) return;

    const screen = document.getElementById('lang-picker-screen');
    if (!screen) return;

    screen.style.display = 'flex';
    _renderLpList();
    _startTitleRotation();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initLangPicker);
else initLangPicker();
