// static/js/rooms/core.js — folder tabs, context menus, panels, discovery, CRUD, members

import { $, api, esc, openModal, closeModal, showAlert } from '../utils.js';
import { showWelcome } from '../ui.js';
import { loadDraft } from '../chat/chat.js';
import { eciesEncrypt, setRoomKey } from '../crypto.js';
import { getUnreadCount, hasMention } from '../notifications.js';
import {
    FOLDER_COLORS, MAX_FOLDERS,
    _getFolders, _setFolders, _getFolderRooms, _setFolderRooms, _nextFolderId,
    assignRoomToFolder, _getRoomFolderId, _getActiveFilterRoomIds,
    _getHiddenRoomIds, _setHiddenRoomIds,
    _getPinnedRoomIds, _setPinnedRoomIds,
    _getArchivedRoomIds, _setArchivedRoomIds,
    _getHiddenHash, _hashPassword,
} from './state.js';

// ── Mutable UI state ─────────────────────────────────────────────────────────

let _activeFolder    = null;   // null = "Все", or folder id
let _editingFolderId = null;   // null = creating, number = editing
let _folderCtxMenu   = null;
let _renderingRooms  = false;  // guard against renderRoomsList <-> renderFolderTabs recursion
let _ctxMenu         = null;
let _hiddenRevealed  = false;
let _hiddenTimer     = null;
let _peerRoomsCache  = {};
let _discoveryTimer  = null;
let _searchQuery     = '';      // текущий поисковый запрос по чатам

// ══════════════════════════════════════════════════════════════════════════════
// Папки — CRUD
// ══════════════════════════════════════════════════════════════════════════════

function createFolder(name, color) {
    const folders = _getFolders();
    if (folders.length >= MAX_FOLDERS) return null;
    const trimmed = (name || '').trim().slice(0, 20);
    if (!trimmed) return null;
    const folder = { id: _nextFolderId(), name: trimmed, color: color || FOLDER_COLORS[0] };
    folders.push(folder);
    _setFolders(folders);
    renderFolderTabs();
    return folder;
}

function updateFolder(id, name, color) {
    const folders = _getFolders();
    const fl = folders.find(f => f.id === id);
    if (!fl) return;
    if (name !== undefined) fl.name = (name || '').trim().slice(0, 20);
    if (color !== undefined) fl.color = color;
    _setFolders(folders);
    renderFolderTabs();
}

function deleteFolder(id) {
    let folders = _getFolders();
    folders = folders.filter(f => f.id !== id);
    _setFolders(folders);
    const map = _getFolderRooms();
    delete map[id];
    _setFolderRooms(map);
    if (_activeFolder === id) _activeFolder = null;
    renderFolderTabs();
    renderRoomsList();
}

// ── Folder tabs rendering ────────────────────────────────────────────────────

export function renderFolderTabs() {
    const el = document.getElementById('folder-tabs');
    if (!el) return;
    const folders = _getFolders();

    let html = '';

    // "Все" tab
    html += `<div class="folder-tab ${_activeFolder === null ? 'active' : ''}"
                 data-folder-id="all">${t('rooms.all')}</div>`;

    // User folders
    for (const f of folders) {
        html += `<div class="folder-tab ${_activeFolder === f.id ? 'active' : ''}"
                      data-folder-id="${f.id}">
                    <span class="folder-dot" style="background:${esc(f.color)};"></span>${esc(f.name)}
                 </div>`;
    }

    // "+" button
    if (folders.length < MAX_FOLDERS) {
        html += `<button class="folder-tab-add" title="${t('folders.createFolder')}" data-folder-action="add">+</button>`;
    }

    el.innerHTML = html;

    // Attach click handlers
    el.querySelectorAll('.folder-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const fid = tab.dataset.folderId;
            _activeFolder = fid === 'all' ? null : parseInt(fid, 10);
            renderFolderTabs();
            renderRoomsList();
        });
        // Right-click on user folder tabs for edit/delete
        tab.addEventListener('contextmenu', (e) => {
            const fid = tab.dataset.folderId;
            if (fid === 'all') return;
            e.preventDefault();
            e.stopPropagation();
            _showFolderContextMenu(e, parseInt(fid, 10));
        });
    });

    const addBtn = el.querySelector('[data-folder-action="add"]');
    if (addBtn) {
        addBtn.addEventListener('click', () => _openFolderModal(null));
    }
}

// ── Folder tab context menu (edit/delete) ────────────────────────────────────

function _showFolderContextMenu(e, folderId) {
    _closeFolderContextMenu();
    const folders = _getFolders();
    const fl = folders.find(f => f.id === folderId);
    if (!fl) return;

    const menu = document.createElement('div');
    menu.className = 'folder-ctx-menu';
    menu.innerHTML = `
        <div class="folder-ctx-item" data-action="edit">${t('folders.rename')}</div>
        <div class="folder-ctx-item danger" data-action="delete">${t('folders.delete')}</div>`;
    menu.style.left = e.clientX + 'px';
    menu.style.top  = e.clientY + 'px';
    document.body.appendChild(menu);
    _folderCtxMenu = menu;

    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) menu.style.left = (window.innerWidth - rect.width - 4) + 'px';
    if (rect.bottom > window.innerHeight) menu.style.top = (window.innerHeight - rect.height - 4) + 'px';

    menu.addEventListener('click', (ev) => {
        const action = ev.target.dataset.action;
        if (action === 'edit')   _openFolderModal(folderId);
        if (action === 'delete') deleteFolder(folderId);
        _closeFolderContextMenu();
    });

    setTimeout(() => {
        document.addEventListener('click', _closeFolderContextMenu, { once: true });
    }, 0);
}

function _closeFolderContextMenu() {
    if (_folderCtxMenu) { _folderCtxMenu.remove(); _folderCtxMenu = null; }
}

// ── Folder create/edit modal ─────────────────────────────────────────────────

function _openFolderModal(folderId) {
    _editingFolderId = folderId;
    const modal    = document.getElementById('folder-modal');
    const titleEl  = document.getElementById('folder-modal-title');
    const nameInp  = document.getElementById('folder-name-input');
    const errorEl  = document.getElementById('folder-modal-error');
    const okBtn    = document.getElementById('folder-modal-ok');
    const colorEl  = document.getElementById('folder-color-picker');
    if (!modal) return;

    const isEdit = folderId !== null;
    let folder = null;
    if (isEdit) {
        folder = _getFolders().find(f => f.id === folderId);
        if (!folder) return;
    }

    titleEl.textContent = isEdit ? t('folders.edit') : t('folders.newFolder');
    nameInp.value = isEdit ? folder.name : '';
    errorEl.textContent = '';
    okBtn.textContent = isEdit ? t('app.save') : t('app.create');

    // Render color swatches
    const selectedColor = isEdit ? folder.color : FOLDER_COLORS[0];
    colorEl.innerHTML = FOLDER_COLORS.map(c =>
        `<div class="folder-color-swatch ${c === selectedColor ? 'selected' : ''}"
              data-color="${c}" style="background:${c};"></div>`
    ).join('');

    colorEl.querySelectorAll('.folder-color-swatch').forEach(sw => {
        sw.addEventListener('click', () => {
            colorEl.querySelectorAll('.folder-color-swatch').forEach(s => s.classList.remove('selected'));
            sw.classList.add('selected');
        });
    });

    modal.style.display = 'flex';
    setTimeout(() => nameInp.focus(), 50);

    // Replace OK button to clear old listeners
    const newBtn = okBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newBtn, okBtn);
    newBtn.id = 'folder-modal-ok';

    const handler = () => {
        const name = nameInp.value.trim();
        if (!name) { errorEl.textContent = t('rooms.enterName'); return; }
        const color = colorEl.querySelector('.folder-color-swatch.selected')?.dataset.color || FOLDER_COLORS[0];

        if (isEdit) {
            updateFolder(folderId, name, color);
        } else {
            if (_getFolders().length >= MAX_FOLDERS) {
                errorEl.textContent = `${t('folders.maxFolders')} ${MAX_FOLDERS}`;
                return;
            }
            createFolder(name, color);
        }
        closeFolderModal();
    };

    newBtn.addEventListener('click', handler);
    nameInp.onkeydown = (e) => { if (e.key === 'Enter') handler(); };
}

function closeFolderModal() {
    const modal = document.getElementById('folder-modal');
    if (modal) modal.style.display = 'none';
    _editingFolderId = null;
}

window.closeFolderModal = closeFolderModal;
window._openFolderModalFromMenu = () => _openFolderModal(null);

let _searchDebounce = null;
window.filterRoomList = function(query) {
    _searchQuery = (query || '').trim().toLowerCase();
    renderRoomsList();

    // Серверный поиск публичных комнат (с debounce)
    clearTimeout(_searchDebounce);
    if (!_searchQuery || _searchQuery.length < 2) {
        _clearServerSearchResults();
        return;
    }
    _searchDebounce = setTimeout(() => _serverSearchRooms(_searchQuery), 300);
};

async function _serverSearchRooms(query) {
    try {
        const data = await api('GET', `/api/global/search-rooms?q=${encodeURIComponent(query)}`);
        const results = data?.rooms || [];
        if (!results.length) { _clearServerSearchResults(); return; }

        const S = window.AppState;
        const myIds = new Set((S.rooms || []).map(r => r.id));
        const external = results.filter(r => !myIds.has(r.id));
        if (!external.length) { _clearServerSearchResults(); return; }

        const el = $('rooms-list');
        if (!el) return;

        // Удаляем старые результаты
        _clearServerSearchResults();

        const label = document.createElement('div');
        label.className = 'rooms-section-label server-search-label';
        label.textContent = t('rooms.globalResults');
        el.appendChild(label);

        for (const r of external) {
            const item = document.createElement('div');
            item.className = 'room-item server-search-item';
            item.dataset.room = r.id;
            item.addEventListener('click', () => {
                if (r.invite_code) {
                    if (r.is_channel) {
                        if (typeof window.joinAndOpenChannel === 'function')
                            window.joinAndOpenChannel(r.invite_code, r.id);
                        else joinPublicRoom(r.id, r.invite_code);
                    } else {
                        joinPublicRoom(r.id, r.invite_code);
                    }
                }
            });

            const isChannel = r.is_channel || r.room_type === 'channel';
            const isVoice = r.is_voice || r.room_type === 'voice';
            const icon = document.createElement('div');
            icon.className = 'room-icon';
            if (r.avatar_url) {
                const img = document.createElement('img');
                img.src = r.avatar_url;
                img.alt = r.name;
                img.style.cssText = 'width:100%;height:100%;border-radius:50%;object-fit:cover;';
                icon.appendChild(img);
            } else {
                icon.textContent = r.avatar_emoji || (isChannel ? '\u{1F4E2}' : isVoice ? '\u{1F3A4}' : '\u{1F4AC}');
            }
            item.appendChild(icon);

            const body = document.createElement('div');
            body.className = 'room-body';
            const nameDiv = document.createElement('div');
            nameDiv.className = 'room-name';
            nameDiv.textContent = r.name;
            body.appendChild(nameDiv);
            const metaDiv = document.createElement('div');
            metaDiv.className = 'room-meta';
            const typeLabel = isChannel ? t('shortcuts.typeChannel') : isVoice ? t('shortcuts.typeVoice') : t('shortcuts.typeRoom');
            metaDiv.textContent = r.description ? typeLabel + ' · ' + r.description : typeLabel;
            body.appendChild(metaDiv);
            item.appendChild(body);

            el.appendChild(item);
        }
    } catch (e) {
        console.warn('server search error', e);
    }
}

function _clearServerSearchResults() {
    const el = $('rooms-list');
    if (!el) return;
    el.querySelectorAll('.server-search-label, .server-search-item').forEach(n => n.remove());
}

// ══════════════════════════════════════════════════════════════════════════════
// Pin / Archive toggles
// ══════════════════════════════════════════════════════════════════════════════

window.togglePinRoom = function(roomId) {
    const ids = _getPinnedRoomIds();
    const idx = ids.indexOf(roomId);
    if (idx === -1) ids.push(roomId);
    else ids.splice(idx, 1);
    _setPinnedRoomIds(ids);
    renderRoomsList();
};

window.toggleArchiveRoom = function(roomId) {
    const ids = _getArchivedRoomIds();
    const idx = ids.indexOf(roomId);
    if (idx === -1) ids.push(roomId);
    else ids.splice(idx, 1);
    _setArchivedRoomIds(ids);
    renderRoomsList();
    _renderArchivePanel();
    _updateArchiveBadge();
};

// ── Контекстное меню комнаты ─────────────────────────────────────────────────

function _showRoomContextMenu(e, roomId) {
    e.preventDefault();
    e.stopPropagation();
    _closeRoomContextMenu();

    const hiddenIds   = _getHiddenRoomIds();
    const isHidden    = hiddenIds.includes(roomId);
    const pinnedIds   = _getPinnedRoomIds();
    const isPinned    = pinnedIds.includes(roomId);
    const archivedIds = _getArchivedRoomIds();
    const isArchived  = archivedIds.includes(roomId);

    let items = '';
    items += isPinned
        ? `<div class="room-ctx-item" data-action="unpin">${t('rooms.unpin')}</div>`
        : `<div class="room-ctx-item" data-action="pin">${t('rooms.pin')}</div>`;
    items += isArchived
        ? `<div class="room-ctx-item" data-action="unarchive">${t('archive.unarchive')}</div>`
        : `<div class="room-ctx-item" data-action="archive">${t('rooms.archive')}</div>`;
    items += isHidden
        ? `<div class="room-ctx-item" data-action="unhide">${t('hidden.showChat')}</div>`
        : `<div class="room-ctx-item" data-action="hide">${t('rooms.hideChat')}</div>`;
    items += `<div class="room-ctx-item" data-action="mark_unread">${t('rooms.markUnread')}</div>`;
    items += `<div class="room-ctx-item" data-action="clear_history" style="color:var(--red);">${t('rooms.clearHistory')}</div>`;

    const _room = window.AppState?.rooms?.find(r => r.id === roomId);

    // Uninstall for bot DMs
    if (_room?.is_dm && _room?.dm_user?.is_bot) {
        items += `<div class="room-ctx-item" data-action="uninstall_bot" style="color:var(--red);">${t('bots.uninstall')}</div>`;
    }

    // Delete DM (anyone can delete their own DM)
    if (_room?.is_dm && !_room?.dm_user?.is_bot) {
        items += `<div class="room-ctx-item" data-action="delete_chat" style="color:var(--red);">${t('app.delete')}</div>`;
    }

    // Leave / Delete room (groups, channels)
    if (_room && !_room.is_dm) {
        const myRole = _room.my_role || _room.role;
        if (myRole === 'owner') {
            items += `<div class="room-ctx-item" data-action="delete_room" style="color:var(--red);">${t('rooms.deleteConfirm').split('?')[0]}</div>`;
        } else {
            items += `<div class="room-ctx-item" data-action="leave_room" style="color:var(--red);">${t('rooms.leave')}</div>`;
        }
    }

    // Folder assignment submenu
    const folders = _getFolders();
    if (folders.length > 0) {
        const currentFid = _getRoomFolderId(roomId);
        let subItems = folders.map(f => {
            const check = f.id === currentFid ? ' <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>' : '';
            return `<div class="room-ctx-subfolder" data-folder-assign="${f.id}">
                        <span class="folder-dot" style="background:${esc(f.color)};display:inline-block;width:6px;height:6px;border-radius:50%;"></span>
                        ${esc(f.name)}${check}
                    </div>`;
        }).join('');
        if (currentFid !== null) {
            subItems += `<div class="room-ctx-subfolder" data-folder-assign="remove" style="color:var(--text3);border-top:1px solid var(--border);margin-top:2px;padding-top:8px;">${t('folders.removeFromFolder')}</div>`;
        }
        items += `<div class="room-ctx-item room-ctx-submenu">${t('folders.folder')} &rarr;
                    <div class="room-ctx-submenu-list" style="display:none;">${subItems}</div>
                  </div>`;
    }

    const menu = document.createElement('div');
    menu.className = 'room-context-menu';
    menu.innerHTML = items;
    menu.style.left = e.clientX + 'px';
    menu.style.top  = e.clientY + 'px';
    document.body.appendChild(menu);
    _ctxMenu = menu;

    // keep menu in viewport
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) menu.style.left = (window.innerWidth - rect.width - 4) + 'px';
    if (rect.bottom > window.innerHeight) menu.style.top = (window.innerHeight - rect.height - 4) + 'px';

    menu.addEventListener('click', async (ev) => {
        const action = ev.target.dataset.action;
        if (action === 'hide')      await hideRoom(roomId);
        if (action === 'unhide')    await unhideRoom(roomId);
        if (action === 'pin')       window.togglePinRoom(roomId);
        if (action === 'unpin')     window.togglePinRoom(roomId);
        if (action === 'archive')   window.toggleArchiveRoom(roomId);
        if (action === 'unarchive') window.toggleArchiveRoom(roomId);
        if (action === 'mark_unread') {
            const S = window.AppState;
            const room = S.rooms?.find(r => r.id === roomId);
            if (room) {
                room.unread_count = Math.max(room.unread_count || 0, 1);
                renderRoomsList();
            }
        }
        if (action === 'clear_history') {
            const S = window.AppState;
            if (S.currentRoom?.id === roomId) {
                const mc = document.getElementById('messages-container');
                if (mc) { while (mc.firstChild) mc.removeChild(mc.firstChild); }
            }
        }
        if (action === 'uninstall_bot') {
            try {
                await api('DELETE', '/api/rooms/' + roomId + '/leave');
                const S = window.AppState;
                S.rooms = S.rooms.filter(r => r.id !== roomId);
                if (S.currentRoom?.id === roomId) {
                    S.currentRoom = null;
                    if (window.showWelcome) window.showWelcome();
                }
                renderRoomsList();
                if (window.showToast) window.showToast(t('bots.uninstalled'), 'success');
            } catch (e) {
                if (window.showToast) window.showToast(t('errors.generic') + ': ' + e.message, 'error');
            }
        }

        if (action === 'delete_chat') {
            try {
                await api('DELETE', '/api/rooms/' + roomId + '/leave');
                const S = window.AppState;
                S.rooms = S.rooms.filter(r => r.id !== roomId);
                if (S.currentRoom?.id === roomId) { S.currentRoom = null; if (window.showWelcome) window.showWelcome(); }
                renderRoomsList();
            } catch (e) {
                if (window.showToast) window.showToast(t('errors.generic') + ': ' + e.message, 'error');
            }
        }
        if (action === 'leave_room') {
            try {
                await api('DELETE', '/api/rooms/' + roomId + '/leave');
                const S = window.AppState;
                S.rooms = S.rooms.filter(r => r.id !== roomId);
                if (S.currentRoom?.id === roomId) { S.currentRoom = null; if (window.showWelcome) window.showWelcome(); }
                renderRoomsList();
            } catch (e) {
                if (window.showToast) window.showToast(t('errors.generic') + ': ' + e.message, 'error');
            }
        }
        if (action === 'delete_room') {
            if (!confirm(t('rooms.deleteConfirm'))) return;
            try {
                await api('DELETE', '/api/rooms/' + roomId);
                const S = window.AppState;
                S.rooms = S.rooms.filter(r => r.id !== roomId);
                if (S.currentRoom?.id === roomId) { S.currentRoom = null; if (window.showWelcome) window.showWelcome(); }
                renderRoomsList();
            } catch (e) {
                if (window.showToast) window.showToast(t('errors.generic') + ': ' + e.message, 'error');
            }
        }

        // Folder assignment
        const folderAssign = ev.target.dataset.folderAssign;
        if (folderAssign === 'remove') {
            assignRoomToFolder(roomId, null);
            renderRoomsList();
        } else if (folderAssign) {
            assignRoomToFolder(roomId, parseInt(folderAssign, 10));
            renderRoomsList();
        }

        // Don't close if hovering over the submenu parent itself (only close on leaf clicks)
        if (!ev.target.classList.contains('room-ctx-submenu')) {
            _closeRoomContextMenu();
        }
    });

    // Show/hide folder submenu on hover
    const submenuItem = menu.querySelector('.room-ctx-submenu');
    if (submenuItem) {
        const submenuList = submenuItem.querySelector('.room-ctx-submenu-list');
        submenuItem.addEventListener('mouseenter', () => {
            if (submenuList) submenuList.style.display = 'block';
            // Adjust submenu position if it goes off-screen
            setTimeout(() => {
                if (!submenuList) return;
                const sr = submenuList.getBoundingClientRect();
                if (sr.right > window.innerWidth) {
                    submenuList.style.left = 'auto';
                    submenuList.style.right = '100%';
                }
                if (sr.bottom > window.innerHeight) {
                    submenuList.style.top = 'auto';
                    submenuList.style.bottom = '0';
                }
            }, 0);
        });
        submenuItem.addEventListener('mouseleave', () => {
            if (submenuList) submenuList.style.display = 'none';
        });
    }

    setTimeout(() => {
        document.addEventListener('click', _closeRoomContextMenu, { once: true });
    }, 0);
}

function _closeRoomContextMenu() {
    if (_ctxMenu) { _ctxMenu.remove(); _ctxMenu = null; }
}

// ══════════════════════════════════════════════════════════════════════════════
// Скрыть / показать комнату
// ══════════════════════════════════════════════════════════════════════════════

export async function hideRoom(roomId) {
    const hash = _getHiddenHash();
    if (!hash) {
        // Первый раз — устанавливаем пароль
        _openHiddenPasswordModal('set', async (pwd) => {
            if (!pwd || pwd.length < 1) return;
            const h = await _hashPassword(pwd);
            localStorage.setItem('vortex_hidden_hash', h);
            const ids = _getHiddenRoomIds();
            if (!ids.includes(roomId)) ids.push(roomId);
            _setHiddenRoomIds(ids);
            renderRoomsList();
            _updateHiddenBadge();
        });
    } else {
        const ids = _getHiddenRoomIds();
        if (!ids.includes(roomId)) ids.push(roomId);
        _setHiddenRoomIds(ids);
        renderRoomsList();
        _updateHiddenBadge();
    }
}

export async function unhideRoom(roomId) {
    const ids = _getHiddenRoomIds().filter(id => id !== roomId);
    _setHiddenRoomIds(ids);
    renderRoomsList();
    _renderHiddenPanel();
    _updateHiddenBadge();
}

export async function showHiddenRooms() {
    const hash = _getHiddenHash();
    if (!hash) return; // no hidden password set

    _openHiddenPasswordModal('check', async (pwd) => {
        const h = await _hashPassword(pwd);
        if (h !== hash) {
            const errEl = document.getElementById('hidden-pwd-error');
            if (errEl) errEl.textContent = t('hidden.wrongPassword');
            return false; // keep modal open
        }
        _hiddenRevealed = true;
        _renderHiddenPanel();
        document.getElementById('hidden-rooms-panel').style.display = '';
        _closeHiddenPasswordModal();

        // auto-hide after 60s
        clearTimeout(_hiddenTimer);
        _hiddenTimer = setTimeout(() => closeHiddenPanel(), 60000);
        return true;
    });
}

export function closeHiddenPanel() {
    _hiddenRevealed = false;
    clearTimeout(_hiddenTimer);
    const panel = document.getElementById('hidden-rooms-panel');
    if (panel) panel.style.display = 'none';
}

function _renderHiddenPanel() {
    const list = document.getElementById('hidden-rooms-list');
    if (!list) return;
    const S = window.AppState;
    const hiddenIds = _getHiddenRoomIds();
    const hiddenRooms = S.rooms.filter(r => hiddenIds.includes(r.id));

    if (!hiddenRooms.length) {
        list.innerHTML = `<div style="padding:16px;color:var(--text3);font-size:12px;">${t('hidden.noHidden')}</div>`;
        return;
    }

    list.innerHTML = hiddenRooms.map(r => {
        const name = r.is_dm ? (r.dm_user?.display_name || r.dm_user?.username || t('chat.dm')) : (r.name || t('rooms.chat'));
        return `
        <div class="hidden-room-item">
            <div class="hidden-room-name" onclick="window.openRoom(${r.id})">${esc(name)}</div>
            <button class="btn btn-secondary btn-sm hidden-room-unhide" onclick="window.unhideRoom(${r.id})">${t('hidden.show')}</button>
        </div>`;
    }).join('');
}

function _updateHiddenBadge() {
    const btn = document.getElementById('hidden-rooms-btn');
    if (!btn) return;
    const count = _getHiddenRoomIds().length;
    btn.style.display = count > 0 ? '' : 'none';
}

// ── Модалка ввода пароля для скрытых чатов ───────────────────────────────────

function _openHiddenPasswordModal(mode, callback) {
    const modal = document.getElementById('hidden-pwd-modal');
    if (!modal) return;
    const title  = document.getElementById('hidden-pwd-title');
    const input  = document.getElementById('hidden-pwd-input');
    const errEl  = document.getElementById('hidden-pwd-error');
    const okBtn  = document.getElementById('hidden-pwd-ok');

    title.textContent = mode === 'set' ? t('hidden.setPassword') : t('hidden.enterPassword');
    input.value = '';
    errEl.textContent = '';
    modal.style.display = 'flex';
    setTimeout(() => input.focus(), 50);

    // remove old listeners by replacing button
    const newBtn = okBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newBtn, okBtn);
    newBtn.id = 'hidden-pwd-ok';

    const handler = async () => {
        const result = await callback(input.value);
        if (result !== false) _closeHiddenPasswordModal();
    };
    newBtn.addEventListener('click', handler);
    input.onkeydown = (e) => { if (e.key === 'Enter') handler(); };
}

function _closeHiddenPasswordModal() {
    const modal = document.getElementById('hidden-pwd-modal');
    if (modal) modal.style.display = 'none';
}

// expose to window
window.hideRoom        = hideRoom;
window.unhideRoom      = unhideRoom;
window.showHiddenRooms = showHiddenRooms;
window.closeHiddenPanel = closeHiddenPanel;
window._closeHiddenPasswordModal = _closeHiddenPasswordModal;

// ══════════════════════════════════════════════════════════════════════════════
// Панель архива
// ══════════════════════════════════════════════════════════════════════════════

export function showArchivePanel() {
    _renderArchivePanel();
    const panel = document.getElementById('archive-rooms-panel');
    if (panel) panel.style.display = '';
}

export function closeArchivePanel() {
    const panel = document.getElementById('archive-rooms-panel');
    if (panel) panel.style.display = 'none';
}

function _renderArchivePanel() {
    const list = document.getElementById('archive-rooms-list');
    if (!list) return;
    const S = window.AppState;
    const archivedIds = _getArchivedRoomIds();
    const archivedRooms = S.rooms.filter(r => archivedIds.includes(r.id));

    if (!archivedRooms.length) {
        list.innerHTML = `<div style="padding:16px;color:var(--text3);font-size:12px;">${t('archive.noArchived')}</div>`;
        return;
    }

    list.innerHTML = archivedRooms.map(r => {
        const name = r.is_dm ? (r.dm_user?.display_name || r.dm_user?.username || t('chat.dm')) : (r.name || t('rooms.chat'));
        return `
        <div class="archive-room-item">
            <div class="archive-room-name" onclick="window.openRoom(${r.id})">${esc(name)}</div>
            <button class="btn btn-secondary btn-sm archive-room-restore" onclick="window.toggleArchiveRoom(${r.id})">${t('archive.unarchive')}</button>
        </div>`;
    }).join('');
}

function _updateArchiveBadge() {
    const btn = document.getElementById('archive-rooms-btn');
    if (btn) {
        const count = _getArchivedRoomIds().length;
        btn.style.display = count > 0 ? '' : 'none';
    }
    // Update reveal badge count
    const countEl = document.getElementById('cs-archived-count');
    if (countEl) {
        const count = _getArchivedRoomIds().length;
        countEl.textContent = count > 0 ? count : '';
        countEl.style.display = count > 0 ? '' : 'none';
    }
}

// Overscroll reveal for archive
(function() {
    var _overscrollActive = false;
    var _touchStartY = 0;

    function _initArchiveReveal() {
        var list = document.getElementById('rooms-list');
        if (!list || list._archiveRevealInit) return;
        list._archiveRevealInit = true;

        list.addEventListener('scroll', function() {
            // Hide when scrolled down
            if (list.scrollTop > 5) _hideArchiveReveal();
        });

        // Wheel overscroll at top
        list.addEventListener('wheel', function(e) {
            if (list.scrollTop <= 0 && e.deltaY < 0) {
                _showArchiveReveal();
            } else if (e.deltaY > 0) {
                _hideArchiveReveal();
            }
        }, { passive: true });

        // Touch overscroll
        list.addEventListener('touchstart', function(e) {
            _touchStartY = e.touches[0].clientY;
        }, { passive: true });

        list.addEventListener('touchmove', function(e) {
            var dy = e.touches[0].clientY - _touchStartY;
            if (list.scrollTop <= 0 && dy > 30) {
                _showArchiveReveal();
            } else if (dy < -10) {
                _hideArchiveReveal();
            }
        }, { passive: true });
    }

    function _showArchiveReveal() {
        if (_getArchivedRoomIds().length === 0) return;
        if (_overscrollActive) return;
        _overscrollActive = true;
        var reveal = document.getElementById('cs-archive-reveal');
        if (reveal) reveal.classList.add('visible');
        // Haptic feedback
        if (window.Haptic?.light) window.Haptic.light();
        else if (navigator.vibrate) navigator.vibrate(10);
    }

    function _hideArchiveReveal() {
        if (!_overscrollActive) return;
        _overscrollActive = false;
        var reveal = document.getElementById('cs-archive-reveal');
        if (reveal) reveal.classList.remove('visible');
    }

    // Init after DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _initArchiveReveal);
    } else {
        setTimeout(_initArchiveReveal, 500);
    }
    // Re-init after renderRoomsList
    var _origRender = window.renderRoomsList;
    if (_origRender) {
        window.renderRoomsList = function() {
            _origRender.apply(this, arguments);
            _initArchiveReveal();
        };
    }
})();

window.showArchivePanel = showArchivePanel;
window.closeArchivePanel = closeArchivePanel;

// ── Avatar helpers ───────────────────────────────────────────────────────────

function _renderRoomItem(r, S, pinnedIds) {
    if (r.is_dm) {
        const u = r.dm_user || {};
        const isBot = u.is_bot;
        const avatar = isBot
            ? `<div class="room-avatar-sidebar" style="background:linear-gradient(135deg,var(--accent),#3b82f6);color:#fff;display:flex;align-items:center;justify-content:center;border-radius:10px;width:36px;height:36px;flex-shrink:0;"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="#fff" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3z"/></svg></div>`
            : _avatarEl(u);
        const badge = isBot ? '<span class="msg-bot-badge" style="margin-left:4px;">BOT</span>' : '';
        const name = esc(u.display_name || u.username || t('chat.dm'));
        return `<div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}" onclick="window.openRoom(${r.id})" data-room="${r.id}">
            ${avatar}
            <div class="room-body"><div class="room-name">${_pinIcon(r.id, pinnedIds)}${name}${badge}</div>
            ${isBot ? '' : `<div class="room-meta">${esc(u.custom_status || t('rooms.dm'))}</div>`}</div>
            ${_unreadBadge(r.id, r.unread_count)}
            ${r.online_count > 0 ? '<div class="online-dot"></div>' : ''}
        </div>`;
    }
    // Group/channel/voice
    const roomAvatarHtml = r.avatar_url
        ? `<div class="room-avatar-sidebar"><img src="${esc(r.avatar_url)}"></div>`
        : (r.avatar_emoji ? `<div class="room-avatar-sidebar">${esc(r.avatar_emoji)}</div>` : `<div class="room-icon"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg></div>`);
    const typeTag = r.is_channel ? `<span class="msg-bot-badge" style="margin-left:4px;background:rgba(59,130,246,.15);color:#60a5fa;">${t('shortcuts.typeChannel')}</span>` : '';
    return `<div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}" onclick="window.openRoom(${r.id})" data-room="${r.id}">
        ${roomAvatarHtml}
        <div class="room-body"><div class="room-name">${_pinIcon(r.id, pinnedIds)}${esc(r.name)}${typeTag}</div>
        <div class="room-meta">${r.member_count || 0} ${t('rooms.membersShort')}</div></div>
        ${r.is_muted ? '<span class="room-muted-icon"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 18.69L7.84 6.14 5.27 3.49 4 4.76l2.8 2.8v.01c-.52.99-.8 2.16-.8 3.42v5l-2 2v1h13.73l2 2L21 19.72l-1-1.03z"/></svg></span>' : ''}
        ${_unreadBadge(r.id, r.unread_count)}
    </div>`;
}

function _avatarEl(obj) {
    const presence = obj.presence || 'online';
    let inner;
    if (obj.avatar_url) {
        inner = `<div class="room-icon dm-avatar"><img src="${esc(obj.avatar_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;"></div>`;
    } else {
        inner = `<div class="room-icon dm-avatar">${esc(obj.avatar_emoji || '\u{1F464}')}</div>`;
    }
    return `<div class="avatar-status-wrap">${inner}<div class="status-dot ${esc(presence)}"></div></div>`;
}

function _memberAvatarEl(obj) {
    if (obj.avatar_url) return `<div class="avatar"><img src="${esc(obj.avatar_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;"></div>`;
    return `<div class="avatar">${esc(obj.avatar_emoji)}</div>`;
}

// ══════════════════════════════════════════════════════════════════════════════
// Авто-обнаружение комнат соседних узлов
// ══════════════════════════════════════════════════════════════════════════════

export function startRoomDiscovery() {
    _discoverPeerRooms();
    _discoveryTimer = setInterval(_discoverPeerRooms, 20_000);
}

async function _discoverPeerRooms() {
    const S = window.AppState;
    if (!S.user) return;

    try {
        await api('POST', '/api/peers/refresh-rooms');
        const data      = await api('GET', '/api/peers/public-rooms');
        const peerRooms = data.rooms || [];

        let hasChanges = false;
        for (const room of peerRooms) {
            const key = `${room.peer_ip}:${room.peer_port}:${room.id}`;
            if (!_peerRoomsCache[key]) {
                _peerRoomsCache[key] = true;
                hasChanges = true;
            }
        }

        const fedRoomsBefore = S.rooms.filter(r => r.is_federated && r._discovery);
        if (fedRoomsBefore.length !== peerRooms.length) hasChanges = true;

        if (hasChanges) await _refreshRoomsQuiet();
    } catch { }
}

async function _refreshRoomsQuiet() {
    const S         = window.AppState;
    const currentId = S.currentRoom?.id;

    try {
        const [localData, fedData, dmData, channelData] = await Promise.allSettled([
            api('GET', '/api/rooms/my'),
            api('GET', '/api/federation/my-rooms'),
            api('GET', '/api/dm/list'),
            api('GET', '/api/channels/my'),
        ]);

        const localRooms = localData.status === 'fulfilled' ? (localData.value.rooms || []) : [];
        const fedRooms   = fedData.status   === 'fulfilled' ? (fedData.value.rooms   || []) : [];
        const dmRooms    = dmData.status    === 'fulfilled' ? (dmData.value.rooms    || []) : [];
        const channels   = channelData.status === 'fulfilled' ? (channelData.value.channels || []) : [];

        S.rooms = [
            ...localRooms,
            ...fedRooms,
            ...dmRooms.map(dm => ({...dm.room, is_dm: true, dm_user: dm.other_user})),
            ...channels.map(ch => ({...ch, is_channel: true})),
        ];

        if (currentId !== undefined) {
            const updated = S.rooms.find(r => r.id === currentId);
            if (updated) S.currentRoom = updated;
        }

        renderRoomsList();
    } catch { }
}

// ══════════════════════════════════════════════════════════════════════════════
// Основные операции с комнатами
// ══════════════════════════════════════════════════════════════════════════════

export async function loadMyRooms() {
    try {
        const [localData, fedData, dmData, channelData] = await Promise.allSettled([
            api('GET', '/api/rooms/my'),
            api('GET', '/api/federation/my-rooms'),
            api('GET', '/api/dm/list'),
            api('GET', '/api/channels/my'),
        ]);

        const localRooms = localData.status === 'fulfilled' ? (localData.value.rooms || []) : [];
        const fedRooms   = fedData.status   === 'fulfilled' ? (fedData.value.rooms   || []) : [];
        const dmRooms    = dmData.status    === 'fulfilled' ? (dmData.value.rooms    || []) : [];
        const channels   = channelData.status === 'fulfilled' ? (channelData.value.channels || []) : [];

        window.AppState.rooms = [
            ...localRooms,
            ...fedRooms,
            ...dmRooms.map(dm => ({...dm.room, is_dm: true, dm_user: dm.other_user})),
            ...channels.map(ch => ({...ch, is_channel: true})),
        ];
        renderRoomsList();
    } catch { }
}

function _unreadBadge(roomId, serverUnread) {
    const clientUnread = getUnreadCount(roomId);
    const count   = Math.max(serverUnread || 0, clientUnread);
    const mention = hasMention(roomId);
    if (!count) return '';
    const label = mention ? `@ ${count}` : count;
    const cls   = mention ? 'unread-badge mention' : 'unread-badge';
    return `<div class="${cls}">${label}</div>`;
}

function _draftPreview(roomId) {
    const draft = loadDraft(roomId);
    if (!draft) return '';
    const trimmed = draft.length > 30 ? draft.slice(0, 30) + '...' : draft;
    return `<div class="room-draft">${t('rooms.draft')}: ${esc(trimmed)}</div>`;
}

function _pinIcon(roomId, pinnedIds) {
    if (!pinnedIds.includes(roomId)) return '';
    return `<span class="room-pin-icon" title="${t('rooms.pinned')}"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg></span>`;
}

export function renderRoomsList() {
    const el = $('rooms-list');
    if (!el) return;
    const S  = window.AppState;

    // Фильтруем скрытые и архивированные комнаты (если не раскрыты)
    const hiddenIds   = _hiddenRevealed ? [] : _getHiddenRoomIds();
    const archivedIds = _getArchivedRoomIds();
    const pinnedIds   = _getPinnedRoomIds();
    let visible     = S.rooms.filter(r => !hiddenIds.includes(r.id) && !archivedIds.includes(r.id));

    // Фильтрация по активной папке
    const folderFilter = _getActiveFilterRoomIds(_activeFolder);
    if (folderFilter !== null) {
        visible = visible.filter(r => folderFilter.includes(r.id));
    }

    // Фильтрация по поисковому запросу
    if (_searchQuery) {
        visible = visible.filter(r => {
            const roomName = (r.name || '').toLowerCase();
            const dmName = (r.dm_user?.display_name || r.dm_user?.username || '').toLowerCase();
            return roomName.includes(_searchQuery) || dmName.includes(_searchQuery);
        });
    }

    // Сортировка: закреплённые наверх внутри каждой секции
    const pinSort = (a, b) => {
        const ap = pinnedIds.includes(a.id) ? 0 : 1;
        const bp = pinnedIds.includes(b.id) ? 0 : 1;
        return ap - bp;
    };

    const grouped = localStorage.getItem('vortex_chat_grouped') !== 'false';

    // Sort by last activity (updated_at or created_at)
    const byActivity = (a, b) => {
        const pinA = pinnedIds.includes(a.id) ? 0 : 1;
        const pinB = pinnedIds.includes(b.id) ? 0 : 1;
        if (pinA !== pinB) return pinA - pinB;
        const tA = new Date(a.updated_at || a.created_at || 0).getTime();
        const tB = new Date(b.updated_at || b.created_at || 0).getTime();
        return tB - tA;
    };

    let html = '';

    if (!grouped) {
        // ── Unified list: all chats sorted by last activity ──
        const all = visible.slice().sort(byActivity);
        html += all.map(r => _renderRoomItem(r, S, pinnedIds)).join('');
    } else {
    // ── Grouped by type ──
    const allDms   = visible.filter(r => r.is_dm);
    const botDms   = allDms.filter(r => r.dm_user?.is_bot).sort(byActivity);
    const dms      = allDms.filter(r => !r.dm_user?.is_bot).sort(byActivity);
    const channels = visible.filter(r => r.is_channel).sort(byActivity);
    const voiceChannels = visible.filter(r => r.is_voice).sort(byActivity);
    const groups   = visible.filter(r => !r.is_dm && !r.is_channel && !r.is_voice).sort(byActivity);

    if (dms.length) {
        html += `<div class="rooms-section-label">${t('rooms.dms')}</div>`;
        html += dms.map(r => {
            const u = r.dm_user || {};
            const richSt = ((u.status_emoji || '') + (u.status_emoji && u.custom_status ? ' ' : '') + (u.custom_status || '')).trim();
            const metaText = richSt || t('rooms.dm');
            return `
            <div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}"
                 onclick="window.openRoom(${r.id})" data-room="${r.id}">
              ${_avatarEl(u)}
              <div class="room-body">
                <div class="room-name">${_pinIcon(r.id, pinnedIds)}${esc(u.display_name || u.username || t('chat.dm'))}</div>
                ${_draftPreview(r.id) || `<div class="room-meta">${esc(metaText)}</div>`}
              </div>
              ${r.is_muted ? `<span class="room-muted-icon" title="${t('rooms.notificationsOff')}"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 18.69L7.84 6.14 5.27 3.49 4 4.76l2.8 2.8v.01c-.52.99-.8 2.16-.8 3.42v5l-2 2v1h13.73l2 2L21 19.72l-1-1.03zM12 22c1.11 0 2-.89 2-2h-4c0 1.11.89 2 2 2zm6-7.32V11c0-3.08-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68c-.15.03-.29.08-.42.12-.1.03-.2.07-.3.11h-.01c-.01 0-.01 0-.02.01-.23.09-.46.2-.68.31 0 0-.01 0-.01.01L18 14.68z"/></svg></span>` : ''}
              ${_unreadBadge(r.id, r.unread_count)}
              ${r.online_count > 0 ? '<div class="online-dot"></div>' : ''}
            </div>`;
        }).join('');
    }

    if (botDms.length) {
        html += `<div class="rooms-section-label">${t('tabs.bots')}</div>`;
        html += botDms.map(r => {
            const u = r.dm_user || {};
            return `
            <div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}"
                 onclick="window.openRoom(${r.id})" data-room="${r.id}">
              <div class="room-avatar-sidebar" style="background:linear-gradient(135deg,var(--accent),#3b82f6);color:#fff;display:flex;align-items:center;justify-content:center;border-radius:10px;width:36px;height:36px;font-size:16px;flex-shrink:0;">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="#fff" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>
              </div>
              <div class="room-body">
                <div class="room-name">${esc(u.display_name || u.username || 'Bot')}<span class="msg-bot-badge" style="margin-left:6px;">BOT</span></div>
                ${_draftPreview(r.id) || ''}
              </div>
              ${_unreadBadge(r.id, r.unread_count)}
            </div>`;
        }).join('');
    }

    if (groups.length) {
        if (dms.length || botDms.length) html += `<div class="rooms-section-label">${t('rooms.rooms')}</div>`;
        html += groups.map(r => {
            const isFed  = r.is_federated;
            // Room avatar: use avatar_url or avatar_emoji, fallback to icon
            const roomAvatarHtml = r.avatar_url
                ? `<div class="room-avatar-sidebar"><img src="${esc(r.avatar_url)}"></div>`
                : (r.avatar_emoji && r.avatar_emoji !== '\u{1F4AC}'
                    ? `<div class="room-avatar-sidebar">${esc(r.avatar_emoji)}</div>`
                    : null);
            const fallbackIcon = isFed
                ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>'
                : (r.is_private
                    ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>'
                    : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>');
            const avatarOrIcon = roomAvatarHtml || `<div class="room-icon">${fallbackIcon}</div>`;
            const fedTag = isFed
                ? `<div style="font-size:10px;color:var(--text3);font-family:var(--mono);">${esc(r.peer_ip || '')}</div>`
                : '';

            return `
            <div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}"
                 onclick="window.openRoom(${r.id})" data-room="${r.id}">
              ${avatarOrIcon}
              <div class="room-body">
                <div class="room-name">${_pinIcon(r.id, pinnedIds)}${esc(r.name)}</div>
                ${_draftPreview(r.id) || `<div class="room-meta">${r.member_count} ${t('rooms.membersShort')} · ${r.online_count} ${t('rooms.online')}</div>`}
                ${fedTag}
              </div>
              ${r.is_muted ? `<span class="room-muted-icon" title="${t('rooms.notificationsOff')}"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 18.69L7.84 6.14 5.27 3.49 4 4.76l2.8 2.8v.01c-.52.99-.8 2.16-.8 3.42v5l-2 2v1h13.73l2 2L21 19.72l-1-1.03zM12 22c1.11 0 2-.89 2-2h-4c0 1.11.89 2 2 2zm6-7.32V11c0-3.08-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68c-.15.03-.29.08-.42.12-.1.03-.2.07-.3.11h-.01c-.01 0-.01 0-.02.01-.23.09-.46.2-.68.31 0 0-.01 0-.01.01L18 14.68z"/></svg></span>` : ''}
              ${_unreadBadge(r.id, r.unread_count)}
              ${r.online_count > 0 ? '<div class="online-dot"></div>' : ''}
            </div>`;
        }).join('');
    }

    if (channels.length) {
        html += `<div class="rooms-section-label">${t('rooms.channels')}</div>`;
        html += channels.map(r => {
            const chAvatarHtml = r.avatar_url
                ? `<div class="room-avatar-sidebar"><img src="${esc(r.avatar_url)}"></div>`
                : (r.avatar_emoji && r.avatar_emoji !== '\u{1F4AC}'
                    ? `<div class="room-avatar-sidebar">${esc(r.avatar_emoji)}</div>`
                    : null);
            const chFallback = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>';
            const chIcon = chAvatarHtml || `<div class="room-icon">${chFallback}</div>`;
            return `
            <div class="room-item ${S.currentRoom?.id === r.id ? 'active' : ''}"
                 onclick="window.openRoom(${r.id})" data-room="${r.id}">
              ${chIcon}
              <div class="room-body">
                <div class="room-name">${_pinIcon(r.id, pinnedIds)}${esc(r.name)}</div>
                ${_draftPreview(r.id) || `<div class="room-meta">${r.subscriber_count || r.member_count || 0} ${t('rooms.subscribers')}</div>`}
              </div>
              ${_unreadBadge(r.id, r.unread_count)}
            </div>`;
        }).join('');
    }

    if (voiceChannels.length) {
        html += `<div class="rooms-section-label">${t('rooms.voice')}</div>`;
        html += voiceChannels.map(r => {
            const vcParticipants = r.voice_participants || [];
            const vcCount = vcParticipants.length;
            const isInVc = typeof window.isInVoiceChannel === 'function' && window.isInVoiceChannel(r.id);
            const vcIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>';

            let participantAvatars = '';
            if (vcCount > 0) {
                participantAvatars = '<div class="vc-sidebar-participants">';
                const shown = vcParticipants.slice(0, 5);
                for (const p of shown) {
                    if (p.avatar_url) {
                        participantAvatars += `<img class="vc-sidebar-avatar" src="${esc(p.avatar_url)}" alt="">`;
                    } else {
                        participantAvatars += `<span class="vc-sidebar-avatar">${esc(p.avatar_emoji || '')}</span>`;
                    }
                }
                if (vcCount > 5) {
                    participantAvatars += `<span class="vc-sidebar-avatar vc-sidebar-more">+${vcCount - 5}</span>`;
                }
                participantAvatars += '</div>';
            }

            const actionBtn = isInVc
                ? `<button class="vc-sidebar-btn vc-sidebar-btn-leave" onclick="event.stopPropagation();leaveVoiceChannel()">${t('rooms.leave')}</button>`
                : `<button class="vc-sidebar-btn vc-sidebar-btn-join" onclick="event.stopPropagation();joinVoiceChannel(${r.id})">${t('rooms.join')}</button>`;

            return `
            <div class="room-item vc-room-item ${isInVc ? 'vc-active' : ''}"
                 onclick="joinVoiceChannel(${r.id})" data-room="${r.id}">
              <div class="room-icon vc-room-icon">${vcIcon}</div>
              <div class="room-body">
                <div class="room-name">${_pinIcon(r.id, pinnedIds)}${esc(r.name)}</div>
                <div class="room-meta">${vcCount > 0 ? vcCount + ' ' + t('rooms.inVoice') : t('rooms.empty')}</div>
                ${participantAvatars}
              </div>
              ${actionBtn}
            </div>`;
        }).join('');
    }
    } // end grouped else

    if (!html) {
        html = _activeFolder !== null
            ? `<div style="padding:12px 16px;color:var(--text3);font-size:12px;font-family:var(--mono);">${t('rooms.emptyFolder')}</div>`
            : `<div style="padding:12px 16px;color:var(--text3);font-size:12px;font-family:var(--mono);">${t('rooms.emptyHint')}</div>`;
    }

    el.innerHTML = html;

    // Привязываем контекстное меню к каждому room-item
    el.querySelectorAll('.room-item[data-room]').forEach(item => {
        item.addEventListener('contextmenu', (e) => {
            const roomId = parseInt(item.dataset.room, 10);
            if (!isNaN(roomId)) _showRoomContextMenu(e, roomId);
        });
    });

    // Обновляем бейджи скрытых и архивных чатов
    _updateHiddenBadge();
    _updateArchiveBadge();

    // Обновляем табы папок (без рекурсии через _renderingRooms guard)
    if (!_renderingRooms) {
        _renderingRooms = true;
        renderFolderTabs();
        _renderingRooms = false;
    }

    // Обновляем коннектор-бар голосового канала
    if (typeof window.renderVoiceConnectorBar === 'function') {
        window.renderVoiceConnectorBar();
    }

    // Если активен спейс — обновляем его sidebar тоже
    if (typeof window._refreshSpaceRoomsIfActive === 'function') {
        window._refreshSpaceRoomsIfActive();
    }
}

// ── Вспомогательные: pubkey ──────────────────────────────────────────────────

async function _ensureUserPubkey() {
    const S = window.AppState;

    // 1. Уже есть в AppState
    if (S.user?.x25519_public_key) return S.user.x25519_public_key;

    // 2. Извлекаем из приватного JWK — надёжнее любого сетевого запроса.
    const privJwkStr = S.x25519PrivateKey || localStorage.getItem('vortex_x25519_priv');
    if (privJwkStr) {
        try {
            const jwk = JSON.parse(privJwkStr);
            if (jwk.x) {
                // base64url → hex
                const b64 = jwk.x.replace(/-/g, '+').replace(/_/g, '/');
                const binary = atob(b64);
                const hex = Array.from(binary, c => c.charCodeAt(0).toString(16).padStart(2, '0')).join('');
                if (S.user) S.user.x25519_public_key = hex;
                console.info('🔑 x25519_public_key восстановлен из локального JWK:', hex.slice(0, 16) + '...');
                return hex;
            }
        } catch (e) {
            console.warn('_ensureUserPubkey: не удалось извлечь pubkey из JWK:', e.message);
        }
    }

    // 3. Последний резерв — обновить данные с сервера (если сервер возвращает pubkey)
    try {
        const fresh = await api('GET', '/api/authentication/me');
        S.user = { ...S.user, ...fresh };
        if (fresh.display_name) {
            const sbName = document.getElementById('sb-name');
            if (sbName) sbName.textContent = fresh.display_name || fresh.username;
        }
    } catch (e) {
        console.warn('_ensureUserPubkey: не удалось обновить данные пользователя:', e.message);
    }

    return S.user?.x25519_public_key || null;
}

// ══════════════════════════════════════════════════════════════════════════════
// Sealed Prekey Packages — zero-metadata key distribution
// ══════════════════════════════════════════════════════════════════════════════

const PREKEY_BATCH = 10;

/**
 * Generate and upload sealed prekey packages for a room.
 * Each package encrypts the room key for a fresh one-time X25519 keypair.
 * New members can claim a package without any online member present.
 */
export async function _uploadSealedPrekeys(roomId, roomKeyBytes) {
    const packages = [];
    for (let i = 0; i < PREKEY_BATCH; i++) {
        // Generate one-time X25519 keypair for this prekey slot
        const oneTimeKey = await crypto.subtle.generateKey(
            { name: 'X25519' }, true, ['deriveBits']
        );
        const pubRaw = await crypto.subtle.exportKey('raw', oneTimeKey.publicKey);
        const recipientPub = Array.from(new Uint8Array(pubRaw)).map(b => b.toString(16).padStart(2, '0')).join('');

        // ECIES encrypt room key for this one-time pubkey
        const enc = await eciesEncrypt(roomKeyBytes, recipientPub);
        packages.push({
            ephemeral_pub: enc.ephemeral_pub,
            ciphertext: enc.ciphertext,
            recipient_pub: recipientPub,
        });
    }

    await api('POST', `/api/rooms/${roomId}/sealed-prekeys`, { packages });
    console.info(`[SealedKeys] ${packages.length} prekeys uploaded for room ${roomId}`);
}

// Handle prekeys_low event — replenish prekeys when running low
window.addEventListener('message', (e) => {
    if (e.data?.type === 'prekeys_low' && e.data.room_id) {
        const roomKey = getRoomKey(e.data.room_id);
        if (roomKey) {
            _uploadSealedPrekeys(e.data.room_id, roomKey).catch(() => {});
        }
    }
});

// ══════════════════════════════════════════════════════════════════════════════
// CRUD комнат
// ══════════════════════════════════════════════════════════════════════════════

export async function createRoom() {
    try {
        const myPubkey = await _ensureUserPubkey();

        if (!myPubkey) {
            throw new Error(t('rooms.keyNotFound'));
        }

        const roomKeyBytes = crypto.getRandomValues(new Uint8Array(32));
        const encryptedKey = await eciesEncrypt(roomKeyBytes, myPubkey);

        const data = await api('POST', '/api/rooms', {
            name:               $('cr-name').value.trim(),
            description:        $('cr-desc').value.trim(),
            is_private:         $('cr-private').checked,
            encrypted_room_key: encryptedKey,
        });

        setRoomKey(data.id, roomKeyBytes);
        if (window.registerRoomSecret) window.registerRoomSecret(data.id);

        // Generate sealed prekey packages for offline key distribution
        _uploadSealedPrekeys(data.id, roomKeyBytes).catch(e =>
            console.warn('[SealedKeys] Prekey upload failed:', e.message)
        );

        window.AppState.rooms.unshift(data);
        renderRoomsList();
        closeModal('create-room-modal');
        window.openRoom(data.id);
        $('cr-name').value = '';
        $('cr-desc').value = '';
    } catch (e) {
        showAlert('cr-alert', e.message);
    }
}

export async function joinRoom() {
    const code = $('join-code').value.trim().toUpperCase();
    if (code.length !== 8) {
        showAlert('join-alert', t('rooms.enterCode'));
        return;
    }
    try {
        const data = await api('POST', `/api/rooms/join/${code}`);
        const room = data.room;
        if (!window.AppState.rooms.find(r => r.id === room.id)) {
            window.AppState.rooms.unshift(room);
        }
        renderRoomsList();
        closeModal('join-modal');
        window.openRoom(room.id);
        $('join-code').value = '';
    } catch (e) {
        showAlert('join-alert', e.message);
    }
}

export async function leaveRoom() {
    const S = window.AppState;
    if (!S.currentRoom) return;

    try {
        const isFed = S.currentRoom.is_federated;

        if (isFed) {
            await api('DELETE', `/api/federation/leave/${S.currentRoom.id}`);
        } else {
            await api('DELETE', `/api/rooms/${S.currentRoom.id}/leave`);
        }

        if (S.ws) {
            S.ws.onclose = null;
            if (S.ws._ping) clearInterval(S.ws._ping);
            S.ws.close();
            S.ws = null;
        }

        S.rooms = S.rooms.filter(r => r.id !== S.currentRoom.id);
        S.currentRoom = null;
        renderRoomsList();
        closeModal('members-modal');
        showWelcome();
    } catch (e) {
        alert(e.message);
    }
}

// ── Публичные комнаты ─────────────────────────────────────────────────────────

function _renderPublicRoomRow(r, isPeer) {
    const peerBadge = isPeer
        ? `<div style="font-size:10px;color:var(--text3);font-family:var(--mono);margin-top:2px;">
               <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:2px;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg> ${esc(r.peer_name || r.peer_ip)}
           </div>`
        : '';

    const joinHandler = isPeer
        ? `window.joinPublicRoom(${r.id},'${r.invite_code}','${r.peer_ip}',${r.peer_port})`
        : `window.joinPublicRoom(${r.id},'${r.invite_code}')`;

    return `
      <div style="padding:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;">
        <div style="font-size:24px;">${r.is_private
            ? '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>'
            : '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>'}</div>
        <div style="flex:1;">
          <div style="font-weight:700;">${esc(r.name)}</div>
          <div style="font-size:12px;color:var(--text2);font-family:var(--mono);">${r.member_count} ${t('rooms.members')}</div>
          ${peerBadge}
        </div>
        <button class="btn btn-primary btn-sm" onclick="${joinHandler}">${t('rooms.joinRoom')}</button>
      </div>`;
}

export async function loadPublicRooms() {
    openModal('public-modal');

    const listEl = $('public-list');
    const isGlobal = window.AppState.user?.network_mode === 'global';

    if (isGlobal) {
        listEl.innerHTML = `
            <div style="padding:12px;">
                <input class="form-input" id="global-room-search" placeholder="${t('rooms.searchPlaceholder')}"
                       oninput="searchGlobalRooms(this.value)" autocomplete="off">
            </div>
            <div id="global-room-results"></div>
        `;
        return;
    }

    listEl.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text2);">${t('app.loading')}</div>`;

    try {
        await api('POST', '/api/peers/refresh-rooms').catch(() => {});

        const [localData, peerData] = await Promise.allSettled([
            api('GET', '/api/rooms/public'),
            api('GET', '/api/peers/public-rooms'),
        ]);

        const localRooms = localData.status === 'fulfilled' ? (localData.value.rooms || []) : [];
        const peerRooms  = peerData.status  === 'fulfilled' ? (peerData.value.rooms  || []) : [];

        if (!localRooms.length && !peerRooms.length) {
            listEl.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text2);">${t('rooms.noPublicRooms')}</div>`;
            return;
        }

        let html = '';

        if (localRooms.length) {
            html += `<div style="padding:8px 12px;font-size:11px;font-weight:700;color:var(--text3);
                         font-family:var(--mono);text-transform:uppercase;letter-spacing:.05em;
                         background:var(--bg2);border-bottom:1px solid var(--border);">
                         <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z"/></svg> ${t('rooms.thisNode')}
                     </div>`;
            html += localRooms.map(r => _renderPublicRoomRow(r, false)).join('');
        }

        if (peerRooms.length) {
            html += `<div style="padding:8px 12px;font-size:11px;font-weight:700;color:var(--text3);
                         font-family:var(--mono);text-transform:uppercase;letter-spacing:.05em;
                         background:var(--bg2);border-bottom:1px solid var(--border);">
                         <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg> ${t('rooms.otherNodes')} (${peerData.value?.peers || 0} ${t('rooms.peers')}) · ${t('rooms.noRegistration')}
                     </div>`;
            html += peerRooms.map(r => _renderPublicRoomRow(r, true)).join('');
        }

        listEl.innerHTML = html;

    } catch (e) {
        listEl.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text2);">${t('rooms.loadError')}: ${esc(e.message)}</div>`;
    }
}

export async function joinPublicRoom(id, code, peerIp, peerPort) {
    try {
        if (peerIp && peerPort) {
            closeModal('public-modal');

            const btn = document.querySelector(`button[onclick*="${code}"]`);
            if (btn) { btn.disabled = true; btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M6 2v6h.01L6 8.01 10 12l-4 4 .01.01H6V22h12v-5.99h-.01L18 16l-4-4 4-3.99-.01-.01H18V2H6zm10 14.5V20H8v-3.5l4-4 4 4zm-4-5l-4-4V4h8v3.5l-4 4z"/></svg>'; }

            let data;
            try {
                data = await api('POST', '/api/peers/federated-join', {
                    invite_code: code,
                    peer_ip:     peerIp,
                    peer_port:   peerPort,
                });
            } catch (directErr) {
                console.warn('Direct federated-join failed, trying multihop:', directErr.message);
                data = await _tryMultihopJoin(code, peerIp, peerPort);

                if (!data) {
                    alert(`${t('rooms.joinFailed')}:\n${directErr.message}`);
                    if (btn) { btn.disabled = false; btn.textContent = t('rooms.joinRoom'); }
                    return;
                }
            }

            const room = data.room;
            if (!window.AppState.rooms.find(r => r.id === room.id)) {
                window.AppState.rooms.unshift(room);
            }

            renderRoomsList();
            window.openRoom(room.id);
            return;
        }

        await api('POST', `/api/rooms/join/${code}`);
        await loadMyRooms();
        closeModal('public-modal');
        window.openRoom(id);

    } catch (e) {
        alert(e.message);
    }
}

async function _tryMultihopJoin(code, targetIp, targetPort) {
    const S     = window.AppState;
    const peers = S.peers || [];

    for (const peer of peers) {
        if (peer.ip === targetIp) continue;
        try {
            console.log(`🔀 Multihop: пробуем через ${peer.ip}:${peer.port} → ${targetIp}:${targetPort}`);
            const data = await api('POST', '/api/peers/multihop-join', {
                invite_code:  code,
                target_ip:    targetIp,
                target_port:  targetPort,
                via_ip:       peer.ip,
                via_port:     peer.port,
            });
            console.log(`✅ Multihop успешен через ${peer.ip}`);
            return data;
        } catch (e) {
            console.warn(`Multihop через ${peer.ip} не удался:`, e.message);
        }
    }

    return null;
}

// ── Вспомогательные ──────────────────────────────────────────────────────────

export function getRoomWsPath(room) {
    return room.is_federated ? `/ws/fed/${room.id}` : `/ws/${room.id}`;
}

export function showCreateRoomModal() {
    openModal('create-room-modal');
    setTimeout(() => $('cr-name').focus(), 50);
}

export function showJoinModal() {
    openModal('join-modal');
    setTimeout(() => $('join-code').focus(), 50);
}

export function copyInviteCode() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    navigator.clipboard.writeText(S.currentRoom.invite_code).then(() => {
        $('modal-invite-code').style.color = 'var(--green)';
        setTimeout(() => $('modal-invite-code').style.color = '', 1000);
    });
}

// ══════════════════════════════════════════════════════════════════════════════
// Управление участниками
// ══════════════════════════════════════════════════════════════════════════════

const _ROLE_PRIORITY = { owner: 3, admin: 2, member: 1 };

function _roleBadge(role) {
    const map = {
        owner:  { label: t('rooms.owner'),  cls: 'member-role-badge--owner'  },
        admin:  { label: t('rooms.admin'),   cls: 'member-role-badge--admin'  },
        member: { label: t('rooms.member'), cls: 'member-role-badge--member' },
    };
    const b = map[role] || map.member;
    return `<span class="member-role-badge ${b.cls}">${b.label}</span>`;
}

function _canActOn(myRole, targetRole, targetId) {
    const S = window.AppState;
    if (targetId === S.user?.id) return false;
    if (targetRole === 'owner') return false;
    const myP = _ROLE_PRIORITY[myRole] || 0;
    const tP  = _ROLE_PRIORITY[targetRole] || 0;
    return myP > tP || (myRole === 'owner');
}

function _memberActionsMenu(m, myRole, roomId) {
    if (!_canActOn(myRole, m.role, m.user_id)) return '';
    const isOwner = myRole === 'owner';

    let items = '';

    // Роль (только owner)
    if (isOwner && !m.is_banned) {
        if (m.role === 'member') {
            items += `<div class="member-actions-item" onclick="window._memberAction('role','${roomId}','${m.user_id}','admin')">${t('rooms.promoteAdmin')}</div>`;
        } else if (m.role === 'admin') {
            items += `<div class="member-actions-item" onclick="window._memberAction('role','${roomId}','${m.user_id}','member')">${t('rooms.demoteAdmin')}</div>`;
        }
    }

    // Мут
    if (!m.is_banned) {
        items += `<div class="member-actions-item" onclick="window._memberAction('mute','${roomId}','${m.user_id}')">${m.is_muted ? t('rooms.unmute') : t('rooms.mute')}</div>`;
    }

    // Бан
    items += `<div class="member-actions-item member-actions-item--danger" onclick="window._memberAction('ban','${roomId}','${m.user_id}')">${m.is_banned ? t('rooms.unban') : t('rooms.ban')}</div>`;

    // Кик (только если не забанен — бан уже кикает)
    if (!m.is_banned) {
        items += `<div class="member-actions-item member-actions-item--danger" onclick="window._memberAction('kick','${roomId}','${m.user_id}')">${t('rooms.kick')}</div>`;
    }

    return `
      <div class="member-actions-wrap">
        <button class="member-actions-btn" onclick="window._toggleMemberMenu(this)" title="${t('rooms.actions')}">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
            <circle cx="8" cy="3" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="8" cy="13" r="1.5"/>
          </svg>
        </button>
        <div class="member-actions-menu">${items}</div>
      </div>`;
}

window._toggleMemberMenu = function(btn) {
    const menu = btn.nextElementSibling;
    // close all other open menus
    document.querySelectorAll('.member-actions-menu.show').forEach(el => {
        if (el !== menu) el.classList.remove('show');
    });
    menu.classList.toggle('show');
};

// Close member menus on outside click
document.addEventListener('click', e => {
    if (!e.target.closest('.member-actions-wrap')) {
        document.querySelectorAll('.member-actions-menu.show').forEach(el => el.classList.remove('show'));
    }
});

window._memberAction = async function(action, roomId, targetId, extra) {
    try {
        if (action === 'role') {
            await api('PUT', `/api/rooms/${roomId}/members/${targetId}/role`, { role: extra });
        } else if (action === 'mute') {
            await api('PUT', `/api/rooms/${roomId}/members/${targetId}/mute`);
        } else if (action === 'ban') {
            await api('PUT', `/api/rooms/${roomId}/members/${targetId}/ban`);
        } else if (action === 'kick') {
            await api('POST', `/api/rooms/${roomId}/kick/${targetId}`);
        }
        // Refresh modal
        showMembersModal();
    } catch (e) {
        alert(e.message);
    }
};

export async function showMembersModal() {
    const S = window.AppState;
    if (!S.currentRoom) return;
    openModal('members-modal');
    $('modal-invite-code').textContent = S.currentRoom.invite_code;

    if (S.currentRoom.is_federated) {
        $('members-list').innerHTML = `<div style="padding:16px;color:var(--text2);font-size:13px;"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg> ${t('rooms.federatedNoMembers')}</div>`;
        return;
    }

    try {
        const data = await api('GET', `/api/rooms/${S.currentRoom.id}/members`);
        const myRole = data.my_role || 'member';
        const roomId = S.currentRoom.id;
        const isPrivileged = (myRole === 'owner' || myRole === 'admin');

        // Sort: owners first, then admins, then members; banned last
        const sorted = data.members.slice().sort((a, b) => {
            if (a.is_banned !== b.is_banned) return a.is_banned ? 1 : -1;
            const pa = _ROLE_PRIORITY[a.role] || 0;
            const pb = _ROLE_PRIORITY[b.role] || 0;
            if (pa !== pb) return pb - pa;
            return (a.display_name || '').localeCompare(b.display_name || '');
        });

        $('members-list').innerHTML = sorted.map(m => {
            const isSelf = m.user_id === S.user?.id;
            const mutedCls = m.is_muted ? ' member-item--muted' : '';
            const bannedCls = m.is_banned ? ' member-item--banned' : '';

            return `
          <div class="member-item${mutedCls}${bannedCls}">
            <div class="member-item-avatar">
              ${_memberAvatarEl(m)}
              <div class="member-online-dot" style="background:${m.is_online ? 'var(--green)' : 'var(--text3)'}"></div>
            </div>
            <div class="member-item-info">
              <div class="member-item-name">
                <span${m.is_banned ? ' style="text-decoration:line-through;"' : ''}>${esc(m.display_name)}</span>
                ${_roleBadge(m.role)}
                ${m.is_muted ? `<span class="member-status-icon" title="${t('rooms.muted')}">&#128263;</span>` : ''}
                ${m.is_banned ? `<span class="member-status-icon" title="${t('rooms.banned')}">&#128683;</span>` : ''}
                ${isSelf ? `<span class="member-you-badge">${t('rooms.you')}</span>` : ''}
              </div>
              <div class="member-item-username">@${esc(m.username)}</div>
            </div>
            ${isPrivileged ? _memberActionsMenu(m, myRole, roomId) : ''}
          </div>`;
        }).join('');
    } catch { }
}

export async function updateRoomMeta() {
    const S = window.AppState;
    if (!S.currentRoom || S.currentRoom.is_federated) return;
    try {
        const data = await api('GET', `/api/rooms/${S.currentRoom.id}`);
        // Preserve client-only fields
        const keep = ['is_dm', 'dm_user', 'is_federated', 'peer_ip', 'has_key', 'is_muted', 'unread_count', 'is_owner', 'is_admin'];
        keep.forEach(k => { if (S.currentRoom[k] !== undefined && data[k] === undefined) data[k] = S.currentRoom[k]; });
        S.currentRoom = data;
        S.rooms = S.rooms.map(r => r.id === data.id ? {...r, ...data} : r);
        renderRoomsList();
        const mc = data.member_count ?? data.subscriber_count ?? 0;
        $('chat-room-meta').textContent = `${mc} ${t('rooms.members')} · ${data.online_count} ${t('rooms.online')}`;
    } catch { }
}

// ── Каналы (создание) ─────────────────────────────────────────────────────────

export function showCreateChannelModal() {
    openModal('create-channel-modal');
    setTimeout(() => $('ch-name').focus(), 50);
}

export async function createChannel() {
    try {
        const myPubkey = await _ensureUserPubkey();
        if (!myPubkey) {
            throw new Error(t('rooms.keyNotFound'));
        }

        const roomKeyBytes = crypto.getRandomValues(new Uint8Array(32));
        const encryptedKey = await eciesEncrypt(roomKeyBytes, myPubkey);

        const data = await api('POST', '/api/channels', {
            name:               $('ch-name').value.trim(),
            description:        $('ch-desc').value.trim(),
            is_private:         $('ch-private').checked,
            encrypted_room_key: encryptedKey,
        });

        setRoomKey(data.id, roomKeyBytes);
        data.is_channel = true;
        data.is_owner   = true;
        data.is_admin   = true;
        window.AppState.rooms.push(data);
        renderRoomsList();
        closeModal('create-channel-modal');
        window.openRoom(data.id);
        $('ch-name').value = '';
        $('ch-desc').value = '';
    } catch (e) {
        showAlert('ch-alert', e.message);
    }
}
