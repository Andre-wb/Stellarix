// static/js/chat/liquid-glass.js
// =============================================================================
// @fileoverview liquid-glass.js
// Легковесная библиотека для создания эффекта «жидкого стекла» (glassmorphism)
// с хроматической аберрацией (SVG-искажение), переливающимся блеском и
// подсветкой, следующей за курсором.
//
// @version 1.0.1
// =============================================================================

/**
 * @typedef {'low'|'mid'|'high'} GpuTier
 */

/**
 * @typedef {Object} LiquidGlassState
 * @property {boolean}               ready
 * @property {boolean}               svgReady
 * @property {boolean}               houdiniReg
 * @property {MutationObserver|null} observer
 * @property {HTMLStyleElement|null} styleEl
 * @property {SVGSVGElement|null}    svgEl
 */

/** @type {LiquidGlassState} */
const _state = {
    ready:      false,
    svgReady:   false,
    houdiniReg: false,
    observer:   null,
    styleEl:    null,
    svgEl:      null,
};

/**
 * @type {Map<HTMLElement, { move: (e: PointerEvent) => void, leave: () => void }>}
 */
const _listenerMap = new Map();

/** @type {GpuTier|null} */
let _gpuTierCache = null;

/**
 * @returns {GpuTier}
 */
function _detectGpuTier() {
    if (_gpuTierCache !== null) return _gpuTierCache;

    const canvas = document.createElement('canvas');
    try {
        const gl = /** @type {WebGLRenderingContext|null} */ (
            canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
        );

        if (!gl) {
            _gpuTierCache = 'low';
            return _gpuTierCache;
        }

        const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
        const dbgInfo  = gl.getExtension('WEBGL_debug_renderer_info');

        if (!dbgInfo) {
            _gpuTierCache = isMobile ? 'low' : 'high';
        } else {
            const renderer = gl.getParameter(dbgInfo.UNMASKED_RENDERER_WEBGL).toLowerCase();

            if (/adreno 3|adreno 4|mali-4|mali-t|powervr sgx|sgx 5/.test(renderer)) {
                _gpuTierCache = 'low';
            } else if (/adreno 5|adreno 6|mali-g5|mali-g7|apple gpu/.test(renderer)) {
                const match = renderer.match(/apple gpu \((\d+)-core\)/);
                _gpuTierCache = (match && parseInt(match[1], 10) >= 10) ? 'high' : 'mid';
            } else {
                _gpuTierCache = 'high';
            }
        }

        gl.getExtension('WEBGL_lose_context')?.loseContext();
    } catch (_) {
        _gpuTierCache = 'low';
    } finally {
        canvas.width  = 0;
        canvas.height = 0;
    }

    return /** @type {GpuTier} */ (_gpuTierCache);
}

function _registerHoudini() {
    if (_state.houdiniReg || !window.CSS?.registerProperty) return;
    _state.houdiniReg = true;

    /** @type {Array<PropertyDefinition>} */
    const props = [
        { name: '--lg-mx',   syntax: '<percentage>', inherits: false, initialValue: '50%'  },
        { name: '--lg-my',   syntax: '<percentage>', inherits: false, initialValue: '30%'  },
        { name: '--lg-irid', syntax: '<angle>',      inherits: false, initialValue: '0deg' },
    ];

    props.forEach(p => {
        try { CSS.registerProperty(p); } catch (_) {}
    });
}

function _buildDistortFilter() {
    return `<defs>
        <filter id="lg-distort" x="-22%" y="-22%" width="144%" height="144%"
                color-interpolation-filters="sRGB">
            <feTurbulence type="turbulence" baseFrequency="0.018 0.022"
                          numOctaves="3" seed="4" result="turb">
                <animate attributeName="baseFrequency"
                    values="0.018 0.022;0.023 0.017;0.018 0.022"
                    dur="8s" repeatCount="indefinite"
                    calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1"/>
                <animate attributeName="seed"
                    values="4;9;2;14;6;4"
                    dur="22s" repeatCount="indefinite"
                    calcMode="discrete"/>
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="turb" scale="5.5"
                               xChannelSelector="R" yChannelSelector="G" result="dR"/>
            <feDisplacementMap in="SourceGraphic" in2="turb" scale="3.8"
                               xChannelSelector="G" yChannelSelector="B" result="dG"/>
            <feDisplacementMap in="SourceGraphic" in2="turb" scale="2.2"
                               xChannelSelector="B" yChannelSelector="R" result="dB"/>
            <feColorMatrix in="dR" type="matrix"
                values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="oR"/>
            <feColorMatrix in="dG" type="matrix"
                values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="oG"/>
            <feColorMatrix in="dB" type="matrix"
                values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="oB"/>
            <feBlend in="oR" in2="oG"            mode="screen" result="rg"/>
            <feBlend in="rg" in2="oB"            mode="screen" result="rgb"/>
            <feComposite in="rgb" in2="SourceGraphic" operator="atop"/>
        </filter>
    </defs>`;
}

function _buildPassthroughFilter() {
    return `<defs><filter id="lg-distort"><feComposite operator="atop"/></filter></defs>`;
}

function _injectSVG() {
    if (_state.svgReady) return;
    _state.svgReady = true;

    const svg = /** @type {SVGSVGElement} */ (
        document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    );
    svg.setAttribute(
        'style',
        'position:fixed;width:0;height:0;overflow:hidden;pointer-events:none;z-index:-1'
    );
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = _detectGpuTier() !== 'low'
        ? _buildDistortFilter()
        : _buildPassthroughFilter();

    document.body.appendChild(svg);
    _state.svgEl = svg;
}

/** @type {string} */
const _CSS = `
.lg-outer {
    display: inline-flex;
    position: relative;
    margin:  -9px;
    padding:  9px;
    filter: url(#lg-distort);
}
.lg-outer.block { display: block; }
.lg-outer.flex  { display: flex;  }
.lg-outer.grid  { display: grid;  }

.lg {
    --lg-mx:   50%;
    --lg-my:   30%;
    --lg-irid: 0deg;
    position:         relative;
    isolation:        isolate;
    overflow:         hidden;
    border-radius:    14px;
    transform:        translateZ(0);
    will-change:      transform;
    background:       rgba(255, 255, 255, 0.035);
    backdrop-filter:         blur(20px) saturate(160%) brightness(1.08);
    -webkit-backdrop-filter: blur(20px) saturate(160%) brightness(1.08);
    border: none;
    box-shadow:
    0  4px 16px -2px  rgba(0, 0, 0, 0.30),
    0 12px 40px -8px  rgba(0, 0, 0, 0.20),
    0  1px  3px       rgba(0, 0, 0, 0.18),
    0  0   36px -14px rgba(180, 160, 255, 0.18);
    transition:
        transform    0.20s cubic-bezier(0.34, 1.56, 0.64, 1),
        box-shadow   0.20s ease,
        background   0.20s ease,
        border-color 0.20s ease;
    animation: lg-irid-spin 12s linear infinite;
}

.lg::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    pointer-events: none;
    z-index: 1;
    background:
        radial-gradient(ellipse 55% 38% at var(--lg-mx) var(--lg-my),
            rgba(255,255,255,0.20) 0%, rgba(255,255,255,0.06) 40%, transparent 64%),
        radial-gradient(ellipse 92% 72% at var(--lg-mx) var(--lg-my),
            rgba(255,255,255,0.04) 0%, transparent 68%),
        linear-gradient(148deg,
            rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.02) 38%,
            transparent 65%, rgba(255,255,255,0.03) 100%);
    transition: background 0.04s linear;
}

.lg::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    pointer-events: none;
    z-index: 2;
    background: conic-gradient(
        from var(--lg-irid) at 50% 50%,
        hsla(210,100%,85%,0.000), hsla(255,100%,90%,0.038),
        hsla(300,100%,85%,0.025), hsla(345,100%,90%,0.038),
        hsla( 30,100%,85%,0.025), hsla( 90,100%,90%,0.038),
        hsla(150,100%,85%,0.025), hsla(210,100%,85%,0.000)
    );
    mix-blend-mode: overlay;
    opacity: 0.9;
    animation: lg-irid-spin 12s linear infinite;
}

.lg-grain {
    position: absolute;
    inset: 0;
    border-radius: inherit;
    pointer-events: none;
    z-index: 3;
    will-change: background-position;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.80' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)' opacity='0.9'/%3E%3C/svg%3E");
    background-size: 200px 200px;
    mix-blend-mode: soft-light;
    opacity: 0.08;
    animation: lg-grain-shift 0.14s steps(1) infinite;
}

.lg > * { position: relative; z-index: 4; }

.lg.lg-interactive { cursor: pointer; }
.lg.lg-interactive:hover {
    background: rgba(255, 255, 255, 0.055);
    border-top-color:  rgba(255, 255, 255, 0.18);
    border-left-color: rgba(255, 255, 255, 0.10);
    box-shadow:
        inset 0  1.5px 0  rgba(255, 255, 255, 0.38),
        inset 1px 0    0  rgba(255, 255, 255, 0.14),
        inset 0 -1px   0  rgba(0, 0, 0, 0.10),
        0  8px 24px -4px  rgba(0, 0, 0, 0.38),
        0 20px 52px -8px  rgba(0, 0, 0, 0.26),
        0  2px  5px       rgba(0, 0, 0, 0.22),
        0  0   52px -14px rgba(160, 130, 255, 0.28);
    transform: translateY(-1.5px) translateZ(0);
}
.lg.lg-interactive:active {
    transform: translateY(0.5px) scale(0.992) translateZ(0);
    transition-duration: 0.08s;
}

.lg-reply {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 7px 11px;
    margin-bottom: 8px;
    border-radius: 8px;
    box-shadow:
        inset 2.5px 0   0 rgba(255,255,255,0.32),
        inset 0     1px 0 rgba(255,255,255,0.14),
        inset 0    -1px 0 rgba(0,0,0,0.10),
        0 2px 8px -2px rgba(0,0,0,0.20);
}
.lg-reply .lg-sender {
    font-size: 11px; font-weight: 700;
    color: rgba(255,255,255,0.82); letter-spacing: 0.015em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    position: relative; z-index: 4;
}
.lg-reply .lg-text {
    font-size: 12px; color: rgba(255,255,255,0.46);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    position: relative; z-index: 4;
}

.lg.lg-own {
    background: rgba(120, 80, 210, 0.05);
    box-shadow:
        inset 0  1.5px 0  rgba(225,195,255,0.22),
        inset 1px 0    0  rgba(200,170,255,0.10),
        inset 0 -1px   0  rgba(0,0,0,0.12),
        0  4px 16px -2px  rgba(0,0,0,0.28),
        0 12px 36px -8px  rgba(0,0,0,0.18),
        0  0   28px -10px rgba(150,100,255,0.18);
}
.lg.lg-own::after {
    background: conic-gradient(
        from var(--lg-irid) at 50% 50%,
        hsla(250,100%,85%,0.000), hsla(280,100%,90%,0.045),
        hsla(310,100%,85%,0.030), hsla(340,100%,90%,0.045),
        hsla(270,100%,85%,0.030), hsla(250,100%,85%,0.000)
    );
}
.lg.lg-own .lg-sender { color: rgba(222,196,255,0.88); }
.lg.lg-own:hover {
    background: rgba(130,90,220,0.08);
    border-top-color: rgba(210,175,255,0.42);
}

@keyframes lg-irid-spin {
    from { --lg-irid:   0deg; }
    to   { --lg-irid: 360deg; }
}
@keyframes lg-grain-shift {
    0%  { background-position:   0px   0px; }
    12% { background-position: -42px -28px; }
    25% { background-position:  28px  46px; }
    37% { background-position: -64px  18px; }
    50% { background-position:  12px -54px; }
    62% { background-position: -36px  66px; }
    75% { background-position:  58px  -8px; }
    87% { background-position: -16px  38px; }
}

@media (prefers-reduced-motion: reduce) {
    .lg            { animation: none; transition: none; }
    .lg::after     { animation: none; }
    .lg-grain      { animation: none; will-change: auto; }
}
`;

function _injectCSS() {
    if (document.getElementById('liquid-glass-style')) return;
    _state.styleEl = Object.assign(document.createElement('style'), {
        id:          'liquid-glass-style',
        textContent: _CSS,
    });
    document.head.appendChild(_state.styleEl);
}

/**
 * @param {HTMLElement} el
 * @returns {void}
 */
function _attachPointerTracking(el) {
    if (_listenerMap.has(el)) return;

    /** @param {PointerEvent} e */
    const onMove = e => {
        const { left, top, width, height } = el.getBoundingClientRect();
        el.style.setProperty('--lg-mx', ((e.clientX - left) / width  * 100).toFixed(1) + '%');
        el.style.setProperty('--lg-my', ((e.clientY - top)  / height * 100).toFixed(1) + '%');
    };

    const onLeave = () => {
        el.style.setProperty('--lg-mx', '50%');
        el.style.setProperty('--lg-my', '30%');
    };

    el.addEventListener('pointermove',  onMove,  { passive: true });
    el.addEventListener('pointerleave', onLeave, { passive: true });

    _listenerMap.set(el, { move: onMove, leave: onLeave });
}

/**
 * @param {HTMLElement} el
 * @returns {void}
 */
function _detachPointerTracking(el) {
    const listeners = _listenerMap.get(el);
    if (!listeners) return;
    el.removeEventListener('pointermove',  listeners.move);
    el.removeEventListener('pointerleave', listeners.leave);
    _listenerMap.delete(el);
}

/**
 * @param {Node} node
 * @returns {void}
 */
function _attachToSubtree(node) {
    if (!(node instanceof HTMLElement)) return;
    if (node.classList.contains('lg')) _attachPointerTracking(node);
    node.querySelectorAll?.('.lg').forEach(_attachPointerTracking);
}

function _startObserver() {
    document.querySelectorAll('.lg').forEach(_attachPointerTracking);

    _state.observer = new MutationObserver(mutations => {
        for (const m of mutations) {
            m.addedNodes.forEach(_attachToSubtree);

            m.removedNodes.forEach(node => {
                if (!(node instanceof HTMLElement)) return;
                if (node.classList.contains('lg')) _detachPointerTracking(node);
                node.querySelectorAll?.('.lg').forEach(_detachPointerTracking);
            });
        }
    });

    _state.observer.observe(document.body, { childList: true, subtree: true });
}

/** @type {Readonly<Record<string, string>>} */
const _BLOCK_DISPLAY_MAP = Object.freeze({
    'flex':        'flex',
    'inline-flex': 'flex',
    'grid':        'grid',
    'inline-grid': 'grid',
});

export function initLiquidGlass() {
    if (_state.ready) return;
    _state.ready = true;

    _registerHoudini();
    _injectSVG();
    _injectCSS();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _startObserver, { once: true });
    } else {
        _startObserver();
    }
}

export function destroyLiquidGlass() {
    _state.observer?.disconnect();

    _listenerMap.forEach((_, el) => _detachPointerTracking(el));

    _state.styleEl?.remove();
    _state.svgEl?.remove();

    _gpuTierCache = null;

    Object.assign(_state, {
        ready:      false,
        svgReady:   false,
        houdiniReg: false,
        observer:   null,
        styleEl:    null,
        svgEl:      null,
    });
}

export function wrapWithDistortion(el) {
    const parent      = el.parentNode;
    const nextSibling = el.nextSibling;

    const wrapper = document.createElement('div');
    wrapper.className = 'lg-outer';

    const display = window.getComputedStyle(el).display;
    const cls     = _BLOCK_DISPLAY_MAP[display];
    if (cls) {
        wrapper.classList.add(cls);
    } else if (display !== 'inline' && display !== 'none') {
        wrapper.classList.add('block');
    }

    parent?.insertBefore(wrapper, el);
    wrapper.appendChild(el);

    function unwrap() {
        if (!wrapper.isConnected) return;
        if (parent) {
            parent.insertBefore(el, nextSibling ?? null);
        } else {
            wrapper.removeChild(el);
        }
        wrapper.remove();
    }

    return { wrapper, unwrap };
}

export function createGrainLayer() {
    return Object.assign(document.createElement('div'), { className: 'lg-grain' });
}

/**
 * Определяет иконку для цитаты по содержимому и типу сообщения.
 * @param {string} text
 * @param {string} [msgType]
 * @returns {string}
 */
function _replyIcon(text, msgType) {
    if (msgType === 'voice' || (text && text.startsWith('voice_'))) return '🎙 ';
    if (msgType === 'image' || /\.(jpg|jpeg|png|gif|webp)/i.test(text || '')) return '🖼 ';
    if (msgType === 'file'  || text === 'файл') return '📄 ';
    return '';
}

/**
 * Создаёт элемент «цитаты» (reply) для использования в сообщениях.
 *
 * @param {string}            sender
 * @param {string}            text
 * @param {boolean}           [isOwn=false]
 * @param {(() => void)|null} [onClick=null]
 * @param {string}            [msgType='']
 * @returns {HTMLDivElement}
 */
export function createReplyQuote(sender, text, isOwn = false, onClick = null, msgType = '') {
    const el = document.createElement('div');
    el.className = `lg lg-reply lg-interactive${isOwn ? ' lg-own' : ''}`;
    el.appendChild(createGrainLayer());

    const senderEl = Object.assign(document.createElement('span'), {
        className:   'lg-sender',
        textContent: sender,
    });

    const icon = _replyIcon(text, msgType);

    const textEl = Object.assign(document.createElement('span'), {
        className:   'lg-text',
        textContent: icon + (text || ''),
    });

    el.append(senderEl, textEl);

    if (typeof onClick === 'function') {
        el.addEventListener('click', e => {
            e.stopPropagation();
            onClick();
        });
    }

    _attachPointerTracking(el);
    return el;
}