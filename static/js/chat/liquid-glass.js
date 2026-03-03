/**
 * liquid-glass.js
 * liquid glass эффект
 * Использует SVG feTurbulence + feDisplacementMap для эффекта воды,
 * backdrop-filter для заморозки стекла, и noise-texture для зернистости.
 */

let _lgStyleInjected = false;
let _lgSvgInjected   = false;

/** Инжектирует CSS и SVG-фильтр один раз */
export function initLiquidGlass() {
    if (_lgStyleInjected) return;
    _lgStyleInjected = true;

    // ── SVG-фильтр для дисторсии (эффект воды на краях) ──────────────────
    if (!_lgSvgInjected) {
        _lgSvgInjected = true;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('style', 'position:absolute;width:0;height:0;overflow:hidden;');
        svg.setAttribute('aria-hidden', 'true');
        svg.innerHTML = `
        <defs>
            <!-- Фильтр дисторсии краёв — эффект преломления воды -->
            <filter id="lg-distort" x="-20%" y="-20%" width="140%" height="140%"
                    color-interpolation-filters="sRGB">
                <feTurbulence type="fractalNoise"
                    baseFrequency="0.65 0.65"
                    numOctaves="3"
                    seed="2"
                    result="noise"/>
                <feDisplacementMap in="SourceGraphic" in2="noise"
                    scale="3.5"
                    xChannelSelector="R"
                    yChannelSelector="G"
                    result="displaced"/>
                <feComposite in="displaced" in2="SourceGraphic" operator="atop"/>
            </filter>

            <!-- Шум для зернистости стекла -->
            <filter id="lg-noise" x="0%" y="0%" width="100%" height="100%">
                <feTurbulence type="fractalNoise"
                    baseFrequency="0.75"
                    numOctaves="4"
                    stitchTiles="stitch"
                    result="noise"/>
                <feColorMatrix type="saturate" values="0" result="grayNoise"/>
                <feBlend in="SourceGraphic" in2="grayNoise" mode="overlay" result="blended"/>
                <feComposite in="blended" in2="SourceGraphic" operator="in"/>
            </filter>
        </defs>`;
        document.body.appendChild(svg);
    }

    // ── CSS стили ─────────────────────────────────────────────────────────
    const style = document.createElement('style');
    style.id = 'liquid-glass-style';
    style.textContent = `

    .lg {
        position: relative;
        isolation: isolate;
        border-radius: 10px;
        overflow: hidden;

        /* Фоновое стекло — заморозка контента под элементом */
        background: rgba(160, 160, 180, 0.08);
        backdrop-filter:
            blur(18px)
            saturate(160%)
            brightness(1.06);
        -webkit-backdrop-filter:
            blur(18px)
            saturate(160%)
            brightness(1.06);

        /* Тонкая граница — как у реального стекла */
        border: 1px solid rgba(255, 255, 255, 0.14);
        box-shadow:
            /* Внутренний блик сверху */
            inset 0  1px 0 rgba(255, 255, 255, 0.22),
            /* Внутренняя тень снизу (глубина) */
            inset 0 -1px 0 rgba(0, 0, 0, 0.12),
            /* Внешняя тень */
            0 4px 24px rgba(0, 0, 0, 0.22),
            0 1px  4px rgba(0, 0, 0, 0.15);

        transition: box-shadow 0.2s ease, background 0.2s ease;
    }

    /* Блик — псевдоэлемент, имитирует отражение в стекле */
    .lg::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: inherit;
        background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.13) 0%,
            rgba(255, 255, 255, 0.04) 40%,
            transparent              70%,
            rgba(255, 255, 255, 0.06) 100%
        );
        pointer-events: none;
        z-index: 1;
    }

    /* Зернистость — как настоящее стекло */
    .lg::after {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: inherit;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
        background-size: 200px 200px;
        opacity: 0.4;
        pointer-events: none;
        z-index: 2;
        mix-blend-mode: overlay;
    }

    /* Контент поверх всех псевдоэлементов */
    .lg > * {
        position: relative;
        z-index: 3;
    }

    /* Hover-состояние */
    .lg.lg-interactive {
        cursor: pointer;
        transition: all 0.18s ease;
    }
    .lg.lg-interactive:hover {
        background: rgba(180, 180, 200, 0.12);
        border-color: rgba(255, 255, 255, 0.22);
        box-shadow:
            inset 0  1px 0 rgba(255, 255, 255, 0.30),
            inset 0 -1px 0 rgba(0, 0, 0, 0.10),
            0 6px 32px rgba(0, 0, 0, 0.28),
            0 2px  6px rgba(0, 0, 0, 0.18);
        transform: translateY(-1px);
    }
    .lg.lg-interactive:active {
        transform: translateY(0px);
        box-shadow:
            inset 0  1px 0 rgba(255, 255, 255, 0.18),
            inset 0 -1px 0 rgba(0, 0, 0, 0.14),
            0 2px 12px rgba(0, 0, 0, 0.20);
    }

    /* ── Вариант для reply-цитаты внутри пузыря ── */
    .lg-reply {
        display: flex;
        flex-direction: column;
        gap: 2px;
        padding: 7px 11px;
        margin-bottom: 8px;
        border-radius: 8px;
        border-left: 2.5px solid rgba(255, 255, 255, 0.35);
    }

    .lg-reply .lg-sender {
        font-size: 11px;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.80);
        letter-spacing: 0.01em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        position: relative;
        z-index: 3;
    }

    .lg-reply .lg-text {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.48);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        position: relative;
        z-index: 3;
    }

    /* ── Тёмный вариант (для своих сообщений с фиолетовым фоном) ── */
    .lg.lg-own {
        background: rgba(120, 80, 200, 0.10);
        border-color: rgba(200, 160, 255, 0.18);
        box-shadow:
            inset 0  1px 0 rgba(220, 180, 255, 0.18),
            inset 0 -1px 0 rgba(0, 0, 0, 0.12),
            0 4px 20px rgba(0, 0, 0, 0.20);
    }
    .lg.lg-own:hover {
        background: rgba(140, 100, 220, 0.14);
        border-color: rgba(200, 160, 255, 0.28);
    }
    .lg.lg-own .lg-sender {
        color: rgba(220, 190, 255, 0.85);
    }
    `;
    document.head.appendChild(style);
}

/**
 * Создаёт DOM-элемент reply-цитаты в стиле liquid glass.
 * @param {string} sender  — имя отправителя
 * @param {string} text    — текст цитируемого сообщения
 * @param {boolean} isOwn  — сообщение своё (другой оттенок стекла)
 * @param {Function} onClick — callback по клику
 * @returns {HTMLElement}
 */
export function createReplyQuote(sender, text, isOwn, onClick) {
    initLiquidGlass();

    const el = document.createElement('div');
    el.className = `lg lg-reply lg-interactive${isOwn ? ' lg-own' : ''}`;

    const senderEl = document.createElement('span');
    senderEl.className   = 'lg-sender';
    senderEl.textContent = sender;

    const textEl = document.createElement('span');
    textEl.className   = 'lg-text';
    textEl.textContent = text;

    el.appendChild(senderEl);
    el.appendChild(textEl);

    el.addEventListener('click', (e) => {
        e.stopPropagation();
        onClick?.();
    });

    return el;
}