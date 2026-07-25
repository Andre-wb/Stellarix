// Stellarix — модальное окно подтверждения опасных действий.
// Перехватывает клики по кнопкам сброса без правок существующего кода.
const StxConfirm = (() => {
    var overlay = null;

    function isEn() {
        return (typeof StxI18n !== 'undefined' && StxI18n.get() === 'en');
    }

    function close() {
        if (!overlay) return;
        var o = overlay;
        overlay = null;
        o.classList.remove('open');
        setTimeout(function () { if (o.parentNode) o.parentNode.removeChild(o); }, 240);
    }

    function show(opts) {
        close();
        var en = isEn();
        var o = document.createElement('div');
        o.className = 'stx-modal-overlay';
        o.innerHTML =
            '<div class="stx-modal" role="dialog" aria-modal="true">' +
                '<div class="stx-modal-title"></div>' +
                '<div class="stx-modal-body"></div>' +
                '<div class="stx-modal-actions">' +
                    '<button type="button" class="stx-modal-btn stx-modal-cancel"></button>' +
                    '<button type="button" class="stx-modal-btn stx-modal-confirm"></button>' +
                '</div>' +
            '</div>';
        o.querySelector('.stx-modal-title').textContent = en ? 'Are you sure?' : 'Вы уверены?';
        o.querySelector('.stx-modal-body').textContent = opts.body || (en ? 'This action cannot be undone.' : 'Это действие нельзя отменить.');
        o.querySelector('.stx-modal-cancel').textContent = en ? 'Cancel' : 'Отказаться';
        o.querySelector('.stx-modal-confirm').textContent = opts.confirmLabel || 'OK';

        o.addEventListener('click', function (e) { if (e.target === o) close(); });
        o.querySelector('.stx-modal-cancel').addEventListener('click', close);
        o.querySelector('.stx-modal-confirm').addEventListener('click', function () {
            close();
            if (opts.onConfirm) opts.onConfirm();
        });
        document.addEventListener('keydown', function esc(e) {
            if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
        });

        document.body.appendChild(o);
        requestAnimationFrame(function () { o.classList.add('open'); });
        overlay = o;
    }

    // Перехват клика на фазе погружения: штатный обработчик кнопки не вызывается,
    // пока пользователь не подтвердит действие в модалке.
    // Существующие обработчики требуют два нажатия («нажмите ещё раз»),
    // поэтому после подтверждения клик пробрасывается дважды подряд.
    function guard(btnId, labels) {
        document.addEventListener('click', function (e) {
            var btn = e.target && e.target.closest ? e.target.closest('#' + btnId) : null;
            if (!btn) return;
            if (btn.dataset.stxConfirmed === '1') { delete btn.dataset.stxConfirmed; return; }
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            var en = isEn();
            show({
                body: en ? labels.bodyEn : labels.bodyRu,
                confirmLabel: en ? labels.confirmEn : labels.confirmRu,
                onConfirm: function () {
                    btn.dataset.stxConfirmed = '1';
                    btn.click();
                    btn.dataset.stxConfirmed = '1';
                    btn.click();
                }
            });
        }, true);
    }

    guard('stats-reset', {
        confirmRu: 'Удалить',
        confirmEn: 'Delete',
        bodyRu: 'Статистика дашборда будет удалена. Это действие нельзя отменить.',
        bodyEn: 'Dashboard statistics will be deleted. This action cannot be undone.'
    });

    guard('reset-key-btn', {
        confirmRu: 'Начать заново',
        confirmEn: 'Start over',
        bodyRu: 'Текущий сеансовый ключ будет забыт. Это действие нельзя отменить.',
        bodyEn: 'The current session key will be forgotten. This action cannot be undone.'
    });

    return { show: show, close: close };
})();
