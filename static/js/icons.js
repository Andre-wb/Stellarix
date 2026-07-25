// Stellarix — SVG-иконки (серые, тонкая линия), заменяют эмодзи в баннерах.
const StxIcons = (() => {
    function icon(inner) {
        return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="vertical-align:-3px" aria-hidden="true">'
            + '<g stroke="#8a8a88" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round">' + inner + '</g>'
            + '</svg>';
    }
    return {
        ok: icon('<circle cx="12" cy="12" r="9"/><path d="M8 12.2l2.6 2.6L16 9.4"/>'),
        warn: icon('<path d="M12 4.2 21 19.2H3L12 4.2Z"/><path d="M12 9.5v4.3"/><circle cx="12" cy="16.6" r="0.6"/>'),
        err: icon('<circle cx="12" cy="12" r="9"/><path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/>'),
        clip: icon('<path d="M20 11.5 11.6 20a5 5 0 0 1-7-7l8.4-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8"/>'),
    };
})();
