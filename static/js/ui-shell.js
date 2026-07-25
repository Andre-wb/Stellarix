// Stellarix — общие элементы интерфейса: журнал событий и модальные окна.

const UILog = (() => {
    let box = null;
    let empty = true;

    function pad(n) { return String(n).padStart(2, '0'); }
    function stamp() {
        const d = new Date();
        return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    }

    return {
        attach(el) { box = el; },
        // kind: undefined | 'ok' | 'warn' | 'err'
        add(text, kind) {
            try { console.log('[Stellarix]', text); } catch (e) {}
            if (!box) return;
            if (empty) { box.textContent = ''; empty = false; }
            const line = document.createElement('div');
            line.className = 'log-line' + (kind ? ' log-' + kind : '');
            const ts = document.createElement('span');
            ts.className = 'log-ts';
            ts.textContent = stamp();
            const msg = document.createElement('span');
            msg.textContent = text;
            line.appendChild(ts);
            line.appendChild(msg);
            box.appendChild(line);
            while (box.children.length > 300) box.removeChild(box.firstChild);
            box.scrollTop = box.scrollHeight;
        },
        clear() {
            if (box) { box.textContent = 'Журнал пуст.'; empty = true; }
        },
    };
})();

const UIModal = (() => {
    let root = null;

    function ensure() {
        if (root) return root;
        root = document.createElement('div');
        root.className = 'modal-backdrop';
        root.innerHTML =
            '<div class="modal" role="dialog" aria-modal="true">' +
            '<div class="modal-title"></div>' +
            '<div class="modal-body"></div>' +
            '<div class="modal-actions"></div>' +
            '</div>';
        root.addEventListener('click', (e) => { if (e.target === root) hide(); });
        document.body.appendChild(root);
        return root;
    }

    function hide() { if (root) root.classList.remove('open'); }

    // show({ title, text | html, buttons: [{ label, primary, onClick }] })
    function show(opts) {
        const r = ensure();
        r.querySelector('.modal-title').textContent = opts.title || 'Предупреждение';
        const body = r.querySelector('.modal-body');
        if (opts.html != null) body.innerHTML = opts.html;
        else body.textContent = opts.text || '';
        const actions = r.querySelector('.modal-actions');
        actions.textContent = '';
        const buttons = (opts.buttons && opts.buttons.length)
            ? opts.buttons
            : [{ label: 'Понятно', primary: true }];
        buttons.forEach((b) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = b.primary ? 'btn btn-primary' : 'btn btn-outline';
            btn.textContent = b.label;
            btn.addEventListener('click', () => {
                hide();
                if (b.onClick) b.onClick();
            });
            actions.appendChild(btn);
        });
        r.classList.add('open');
    }

    return { show, hide };
})();
