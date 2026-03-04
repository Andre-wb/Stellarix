// static/js/peers.js
// ============================================================================
// Модуль для обнаружения устройств в локальной сети (LAN peers).
// Периодически опрашивает API /api/peers и отображает список найденных пиров.
// ============================================================================

import { $, api, esc } from './utils.js';

// ============================================================================
// PEERS (LAN discovery)
// ============================================================================

/**
 * Запускает периодический опрос пиров.
 * Вызывается после успешной аутентификации в main.js.
 */
export function startPeerPolling() {
    loadPeers();
    window.AppState.peersInterval = setInterval(loadPeers, 5000);
}

/**
 * Загружает список пиров с сервера и обновляет интерфейс.
 */
export async function loadPeers() {
    try {
        const data = await api('GET', '/api/peers');
        window.AppState.peers = data.peers;
        renderPeers();
        updateNetStatus();
    } catch { }
}

/**
 * Отрисовывает список пиров в панели.
 */
function renderPeers() {
    const el = $('peers-list');
    const peers = window.AppState.peers;
    el.innerHTML = peers.length ? peers.map(p => `
    <div class="peer-item">
      <div class="peer-dot"></div>
      <div>
        <div class="peer-name">${esc(p.name)}</div>
        <div class="peer-ip">${p.ip}:${p.port}</div>
      </div>
    </div>
  `).join('') : `<div style="padding:20px;text-align:center;color:var(--text3);font-size:12px;font-family:var(--mono);">
    Нет устройств в сети.<br>Убедитесь, что вы в одной Wi-Fi сети.
  </div>`;
}

/**
 * Обновляет статус сети в боковой панели (количество пиров, цвет индикатора).
 */
function updateNetStatus() {
    const n = window.AppState.peers.length;
    const dot = $('net-dot');
    $('peers-badge').textContent = n;
    $('net-label').textContent = n === 0 ? 'Нет устройств' : `${n} устр. в сети`;
    dot.className = 'net-dot ' + (n > 0 ? 'online' : 'offline');
}

/**
 * Переключает видимость панели пиров.
 */
export function togglePeersPanel() {
    $('peers-panel').classList.toggle('show');
}