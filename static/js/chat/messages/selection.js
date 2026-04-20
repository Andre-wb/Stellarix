// =============================================================================
// Мульти-выбор сообщений (bulk delete / bulk forward)
// =============================================================================

let _selectionMode    = false;
const _selectedMsgIds = new Set();

/**
 * Включает режим множественного выбора.
 */
export function _enterSelectionMode() {
    if (_selectionMode) return;
    _selectionMode = true;
    _selectedMsgIds.clear();

    document.querySelectorAll('.msg-group[data-msg-id]').forEach(group => {
        const id = group.dataset.msgId;
        if (id) _addCheckbox(group, id);
    });

    document.getElementById('messages-container')?.classList.add('selection-mode');
    _showSelectionToolbar();
}

/**
 * Выключает режим выбора.
 */
export function _exitSelectionMode() {
    if (!_selectionMode) return;
    _selectionMode = false;
    _selectedMsgIds.clear();

    document.querySelectorAll('.msg-select-checkbox').forEach(cb => cb.remove());
    document.querySelectorAll('.msg-group').forEach(g => g.classList.remove('msg-selected'));
    document.getElementById('messages-container')?.classList.remove('selection-mode');

    _hideSelectionToolbar();
}

function _addCheckbox(groupEl, msgId) {
    if (groupEl.querySelector('.msg-select-checkbox')) return;
    const cb = document.createElement('div');
    cb.className = 'msg-select-checkbox';
    cb.dataset.msgId = msgId;
    cb.setAttribute('role', 'checkbox');
    cb.setAttribute('aria-checked', 'false');
    cb.addEventListener('click', (e) => {
        e.stopPropagation();
        _toggleMessageSelection(msgId, groupEl, cb);
    });
    groupEl.insertBefore(cb, groupEl.firstChild);
}

function _toggleMessageSelection(msgId, groupEl, cbEl) {
    if (_selectedMsgIds.has(msgId)) {
        _selectedMsgIds.delete(msgId);
        groupEl.classList.remove('msg-selected');
        cbEl.classList.remove('checked');
        cbEl.setAttribute('aria-checked', 'false');
    } else {
        _selectedMsgIds.add(msgId);
        groupEl.classList.add('msg-selected');
        cbEl.classList.add('checked');
        cbEl.setAttribute('aria-checked', 'true');
    }
    _updateSelectionCount();
}

function _updateSelectionCount() {
    const el = document.getElementById('selection-count');
    if (el) el.textContent = t('chat.selected', {count: _selectedMsgIds.size});
}

function _showSelectionToolbar() {
    let toolbar = document.getElementById('selection-toolbar');
    if (toolbar) { toolbar.classList.add('visible'); _updateSelectionCount(); return; }

    toolbar = document.createElement('div');
    toolbar.id = 'selection-toolbar';
    toolbar.className = 'selection-toolbar visible';
    toolbar.innerHTML = `
        <span id="selection-count" class="selection-count">Выбрано: 0</span>
        <div class="selection-actions">
            <button class="selection-btn" id="selection-forward-btn">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M14 8H10C5.58 8 2 11.58 2 16v2h2v-2c0-3.31 2.69-6 6-6h4v3l5-4-5-4v3z"/></svg>
                Переслать
            </button>
            <button class="selection-btn danger" id="selection-delete-btn">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM8 9h8v10H8V9zm7.5-5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                Удалить
            </button>
            <button class="selection-btn cancel" id="selection-cancel-btn">✕ Отмена</button>
        </div>`;

    const inputArea = document.getElementById('input-area');
    if (inputArea?.parentNode) {
        inputArea.parentNode.insertBefore(toolbar, inputArea);
    } else {
        document.body.appendChild(toolbar);
    }

    document.getElementById('selection-forward-btn').addEventListener('click', _bulkForward);
    document.getElementById('selection-delete-btn').addEventListener('click', _bulkDelete);
    document.getElementById('selection-cancel-btn').addEventListener('click', _exitSelectionMode);
}

function _hideSelectionToolbar() {
    document.getElementById('selection-toolbar')?.classList.remove('visible');
}

function _bulkDelete() {
    const ids = [..._selectedMsgIds];
    if (!ids.length) return;
    if (ids.length > 3 && !confirm(t('chat.deleteMessages', {count: ids.length}))) return;

    const S = window.AppState;
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    ids.forEach(msgId => S.ws.send(JSON.stringify({ action: 'delete_message', msg_id: msgId })));
    _exitSelectionMode();
}

function _bulkForward() {
    const ids = [..._selectedMsgIds];
    if (!ids.length) return;

    const S = window.AppState;
    const currentId = S.currentRoom?.id;
    const targets = (S.rooms || []).filter(r => r.id !== currentId);

    let html = '';
    targets.forEach(r => {
        const icon = r.avatar_emoji || (r.is_dm ? '👤' : '💬');
        html += `<div class="forward-room-item"
            onclick="window._bulkForwardTo(${JSON.stringify(ids)}, ${r.id})"
            style="padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;">
            <span style="font-size:22px;">${icon}</span>
            <span>${r.name || r.username || '?'}</span>
        </div>`;
    });
    if (!html) html = '<div style="padding:14px;color:var(--text2);">' + t('chat.noAvailableChats') + '</div>';

    let modal = document.getElementById('bulk-forward-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'bulk-forward-modal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal" style="max-width:360px;">
                <div class="modal-title">Переслать в...</div>
                <div id="bulk-forward-list" style="max-height:320px;overflow-y:auto;"></div>
                <div style="padding:12px;">
                    <button class="btn btn-secondary"
                        onclick="document.getElementById('bulk-forward-modal').style.display='none'">
                        Отмена
                    </button>
                </div>
            </div>`;
        document.body.appendChild(modal);
    }
    document.getElementById('bulk-forward-list').innerHTML = html;
    modal.style.display = 'flex';
}

// Expose for external use (e.g. header button)
window._enterSelectionMode = _enterSelectionMode;
window._exitSelectionMode  = _exitSelectionMode;

window._bulkForwardTo = function(msgIds, targetRoomId) {
    const S = window.AppState;
    if (!S.ws || S.ws.readyState !== WebSocket.OPEN) return;
    msgIds.forEach(msgId =>
        S.ws.send(JSON.stringify({ action: 'forward', msg_id: msgId, target_room_id: targetRoomId }))
    );
    const modal = document.getElementById('bulk-forward-modal');
    if (modal) modal.style.display = 'none';
    _exitSelectionMode();
};

// Single-message forward — called from the message context menu ("Forward").
// Shares the same modal as bulk forward; we just stage one id into
// _selectedMsgIds and reuse _bulkForward() for rendering, then wipe the
// staging so the selection UI doesn't show a lingering "1 selected" badge.
window.showForwardModal = function(msgId) {
    if (!msgId) return;
    _selectedMsgIds.clear();
    _selectedMsgIds.add(msgId);
    _bulkForward();
    // Keep the id in the set so _bulkForwardTo still has something to read;
    // clear it after the modal closes (on any target click or Cancel).
    const modal = document.getElementById('bulk-forward-modal');
    if (modal) {
        const cleanup = () => { _selectedMsgIds.clear(); };
        modal.querySelectorAll('.forward-room-item, .btn-secondary')
            .forEach(el => el.addEventListener('click', cleanup, { once: true }));
    }
};

/**
 * Вешает long-press (500 мс) и Shift+click на .msg-group для входа в режим выбора.
 * Вызывается из appendMessage и appendFileMessage сразу после создания элемента.
 */
export function _attachSelectionLongPress(groupEl, msgId) {
    if (!msgId) return;

    let pressTimer = null;

    const _onLongPress = () => {
        if (navigator.vibrate) navigator.vibrate(30);
        if (!_selectionMode) _enterSelectionMode();
        const cb = groupEl.querySelector('.msg-select-checkbox');
        if (cb) _toggleMessageSelection(msgId, groupEl, cb);
    };

    // Mobile long-press
    groupEl.addEventListener('touchstart', () => {
        pressTimer = setTimeout(_onLongPress, 500);
    }, { passive: true });
    groupEl.addEventListener('touchend',    () => clearTimeout(pressTimer), { passive: true });
    groupEl.addEventListener('touchmove',   () => clearTimeout(pressTimer), { passive: true });
    groupEl.addEventListener('touchcancel', () => clearTimeout(pressTimer), { passive: true });

    // Desktop Shift+click — enter selection and toggle this message
    groupEl.addEventListener('click', (e) => {
        if (e.shiftKey) {
            e.preventDefault();
            e.stopPropagation();
            if (!_selectionMode) _enterSelectionMode();
            const cb = groupEl.querySelector('.msg-select-checkbox');
            if (cb) _toggleMessageSelection(msgId, groupEl, cb);
            return;
        }
        // In selection mode: any click on the group body toggles selection
        if (_selectionMode && !e.target.closest('.msg-select-checkbox')) {
            e.stopPropagation();
            const cb = groupEl.querySelector('.msg-select-checkbox');
            if (cb) _toggleMessageSelection(msgId, groupEl, cb);
        }
    });
}
