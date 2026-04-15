window.ideLoad         = ideLoad;
window.ideToggleDocs   = ideToggleDocs;
window.ideToggleSim    = ideToggleSim;
window.ideShowCreateModal = ideShowCreateModal;

// ── Bot Analytics ──────────────────────────────────────────────────────────

async function ideLoadAnalytics(projectId) {
  if (!projectId) return;
  try {
    const res = await fetch(`/api/ide/analytics/${projectId}`, {
      headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || '') }
    });
    if (!res.ok) return;
    const data = await res.json();
    ideShowAnalytics(data);
  } catch (e) {
    console.error('Analytics load failed:', e);
  }
}

function ideShowAnalytics(data) {
  const m = data.metrics || {};
  const status = data.status || {};

  let html = `
    <div class="ide-analytics">
      <div class="ide-analytics-header">
        <span class="ide-status-badge ide-status-${status.status || 'stopped'}">${status.status || 'stopped'}</span>
        ${status.uptime_seconds ? `<span class="ide-uptime">Uptime: ${formatUptime(status.uptime_seconds)}</span>` : ''}
      </div>
      <div class="ide-analytics-grid">
        <div class="ide-metric"><span class="ide-metric-value">${m.messages_processed || 0}</span><span class="ide-metric-label">Messages</span></div>
        <div class="ide-metric"><span class="ide-metric-value">${m.commands_processed || 0}</span><span class="ide-metric-label">Commands</span></div>
        <div class="ide-metric"><span class="ide-metric-value">${m.callbacks_processed || 0}</span><span class="ide-metric-label">Callbacks</span></div>
        <div class="ide-metric ide-metric-error"><span class="ide-metric-value">${m.errors || 0}</span><span class="ide-metric-label">Errors</span></div>
      </div>
      ${data.recent_logs && data.recent_logs.length ? `
        <div class="ide-analytics-logs">
          <div class="ide-analytics-logs-title">Recent Logs</div>
          <pre class="ide-log-output">${data.recent_logs.slice(-20).join('\n')}</pre>
        </div>
      ` : ''}
    </div>
  `;

  // Try to inject into existing IDE panel, or create a modal
  let panel = document.getElementById('ide-analytics-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'ide-analytics-panel';
    panel.className = 'ide-analytics-panel';
    panel.style.cssText = 'position:fixed;top:60px;right:20px;width:320px;background:var(--bg-secondary,#1e1e2e);border:1px solid var(--border-color,#333);border-radius:12px;padding:16px;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,.4);';
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <strong style="color:var(--text-primary,#fff)">Bot Analytics</strong>
        <button onclick="document.getElementById('ide-analytics-panel').remove()" style="background:none;border:none;color:var(--text-secondary,#aaa);cursor:pointer;font-size:18px">×</button>
      </div>
      <div id="ide-analytics-content"></div>
    `;
    document.body.appendChild(panel);
  }
  document.getElementById('ide-analytics-content').innerHTML = html;
}

function formatUptime(secs) {
  if (secs < 60) return secs + 's';
  if (secs < 3600) return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
  return Math.floor(secs / 3600) + 'h ' + Math.floor((secs % 3600) / 60) + 'm';
}

// ══════════════════════════════════════════════════════════════
//  Feature 10: Bot Versioning + Rollback
// ══════════════════════════════════════════════════════════════

async function ideShowVersions() {
    if (!IDE.current) return;
    const pid = _ideProjectId();

    let versions = [];
    try {
        const r = await fetch(`/api/ide/versions/${pid}`, {
            headers: { 'X-CSRF-Token': _csrfToken() },
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const d = await r.json();
        versions = d.versions || [];
    } catch (e) {
        ideShowToast('Could not load versions: ' + e.message, 'warn');
        return;
    }

    // Build modal HTML
    const rows = versions.length === 0
        ? '<div style="color:var(--text3,#888);padding:12px 0;">No saved versions yet.</div>'
        : versions.map(v => {
            const dt = new Date(v.saved_at).toLocaleString();
            const kb = (v.size / 1024).toFixed(1);
            return `<div class="ide-ver-row">
                <div class="ide-ver-info">
                    <span class="ide-ver-num">v${v.version}</span>
                    <span class="ide-ver-date">${_esc(dt)}</span>
                    <span class="ide-ver-size">${kb} KB</span>
                </div>
                <button class="ide-ver-btn" onclick="ideRollback(${v.version})">Restore</button>
            </div>`;
        }).join('');

    _ideShowModal('ide-versions-modal', `
        <div class="ide-modal-header">
            <span>Saved Versions</span>
            <button class="ide-modal-close" onclick="_ideCloseModal('ide-versions-modal')">×</button>
        </div>
        <div class="ide-ver-list">${rows}</div>
        <div class="ide-modal-footer">
            <button class="ide-btn-secondary" onclick="ideSaveVersion()">Save Current</button>
            <button class="ide-btn-primary" onclick="_ideCloseModal('ide-versions-modal')">Close</button>
        </div>
    `);
}

async function ideSaveVersion() {
    if (!IDE.current) return;
    const pid  = _ideProjectId();
    const code = _ideAllCode();
    try {
        const r = await fetch(`/api/ide/save/${pid}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrfToken() },
            body: JSON.stringify({ code }),
        });
        const d = await r.json();
        if (d.ok) {
            ideShowToast(`Saved as v${d.version}`, 'ok');
            // Refresh the list if modal is open
            const modal = document.getElementById('ide-versions-modal');
            if (modal && modal.style.display !== 'none') ideShowVersions();
        } else {
            ideShowToast('Save failed', 'warn');
        }
    } catch (e) {
        ideShowToast('Save error: ' + e.message, 'warn');
    }
}

async function ideRollback(version) {
    if (!IDE.current) return;
    if (!confirm((typeof t==='function'?t('ide.restoreVersionConfirm'):'Restore version') + ` v${version}?`)) return;
    const pid = _ideProjectId();
    try {
        const r = await fetch(`/api/ide/rollback/${pid}/${version}`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': _csrfToken() },
        });
        const d = await r.json();
        if (!d.ok) throw new Error(d.detail || d.error || 'Rollback failed');

        // Restore code into current active file (or main.grav)
        const targetFile = IDE.activeFile || Object.keys(IDE.current.files)[0];
        if (targetFile) {
            IDE.current.files[targetFile] = d.code;
            ideSave();
            const ta = document.getElementById('ide-textarea');
            if (ta) {
                ta.value = d.code;
                ideUpdateHighlight();
                ideUpdateGutter();
                ideLintCode(d.code);
            }
        }
        _ideCloseModal('ide-versions-modal');
        ideShowToast(`Restored v${version}`, 'ok');
    } catch (e) {
        ideShowToast('Rollback error: ' + e.message, 'warn');
    }
}

// ══════════════════════════════════════════════════════════════
//  Feature 11: Visual Flow Graph
// ══════════════════════════════════════════════════════════════

async function ideShowGraph() {
    if (!IDE.current) return;
    const pid = _ideProjectId();

    let graph = { nodes: [], edges: [] };
    try {
        // First autosave so the server file is up-to-date
        ideAutosave();
        const r = await fetch(`/api/ide/graph/${pid}`, {
            headers: { 'X-CSRF-Token': _csrfToken() },
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        graph = await r.json();
    } catch (e) {
        ideShowToast('Could not load graph: ' + e.message, 'warn');
        return;
    }

    const svgContent = _renderGraphSVG(graph.nodes || [], graph.edges || []);

    _ideShowModal('ide-graph-modal', `
        <div class="ide-modal-header">
            <span>Flow Graph</span>
            <button class="ide-modal-close" onclick="_ideCloseModal('ide-graph-modal')">×</button>
        </div>
        <div class="ide-graph-wrap" style="overflow:auto;padding:12px;">
            ${svgContent}
        </div>
        <div class="ide-modal-footer">
            <button class="ide-btn-primary" onclick="_ideCloseModal('ide-graph-modal')">Close</button>
        </div>
    `);
}

function _renderGraphSVG(nodes, edges) {
    if (nodes.length === 0) {
        return '<div style="color:var(--text3,#888);padding:20px;text-align:center;">No graph data — publish or compile the project first.</div>';
    }

    const NODE_W = 140, NODE_H = 36, PAD = 20;
    const TYPE_COLORS = {
        handler:  { fill: '#7c3aed', stroke: '#a78bfa' },
        flow:     { fill: '#0ea5e9', stroke: '#38bdf8' },
        function: { fill: '#059669', stroke: '#34d399' },
        state:    { fill: '#d97706', stroke: '#fbbf24' },
    };

    // Layout: columns by type
    const cols = { handler: [], flow: [], function: [], state: [] };
    nodes.forEach(n => {
        const key = n.type in cols ? n.type : 'function';
        cols[key].push(n);
    });

    const colOrder = ['handler', 'flow', 'function', 'state'];
    const positions = {};
    let x = PAD;

    colOrder.forEach(colKey => {
        const col = cols[colKey];
        if (!col.length) return;
        col.forEach((n, i) => {
            positions[n.id] = { x, y: PAD + i * (NODE_H + PAD) };
        });
        x += NODE_W + PAD * 3;
    });

    // SVG dimensions
    const maxY = Math.max(...Object.values(positions).map(p => p.y)) + NODE_H + PAD;
    const svgW = x;
    const svgH = Math.max(maxY, 120);

    // Build SVG
    let svgEdges = '';
    edges.forEach(e => {
        const from = positions[e.from] || positions['current'];
        const to   = positions[e.to];
        if (!to) return;
        const fx = from ? from.x + NODE_W : PAD;
        const fy = from ? from.y + NODE_H / 2 : PAD + NODE_H / 2;
        const tx = to.x;
        const ty = to.y + NODE_H / 2;
        const mx = (fx + tx) / 2;
        svgEdges += `<path d="M${fx},${fy} C${mx},${fy} ${mx},${ty} ${tx},${ty}"
            fill="none" stroke="#6b7280" stroke-width="1.5" marker-end="url(#arr)" opacity="0.7"/>`;
    });

    let svgNodes = '';
    nodes.forEach(n => {
        const pos = positions[n.id];
        if (!pos) return;
        const c = TYPE_COLORS[n.type] || TYPE_COLORS.function;
        const label = n.label.length > 18 ? n.label.slice(0, 16) + '…' : n.label;
        svgNodes += `
        <g transform="translate(${pos.x},${pos.y})">
            <rect width="${NODE_W}" height="${NODE_H}" rx="6"
                fill="${c.fill}" stroke="${c.stroke}" stroke-width="1.5" opacity="0.9"/>
            <text x="${NODE_W / 2}" y="${NODE_H / 2 + 5}" text-anchor="middle"
                font-family="monospace" font-size="12" fill="#fff">${_esc(label)}</text>
        </g>`;
    });

    // Legend
    const legendItems = colOrder
        .filter(k => cols[k].length > 0)
        .map(k => {
            const c = TYPE_COLORS[k];
            return `<g><rect width="12" height="12" rx="2" fill="${c.fill}" stroke="${c.stroke}" stroke-width="1"/>
                <text x="17" y="11" font-family="sans-serif" font-size="11" fill="#ccc">${_esc(k)}</text></g>`;
        });

    let legendX = PAD;
    const legendSvg = legendItems.map(item => {
        const out = `<g transform="translate(${legendX}, 0)">${item}</g>`;
        legendX += 80;
        return out;
    }).join('');

    return `<svg width="${svgW}" height="${svgH + 30}" xmlns="http://www.w3.org/2000/svg"
        style="background:#111827;border-radius:8px;display:block;">
        <defs>
            <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L9,3 z" fill="#6b7280"/>
            </marker>
        </defs>
        ${svgEdges}
        ${svgNodes}
        <g transform="translate(${PAD}, ${svgH + 8})">${legendSvg}</g>
    </svg>`;
}


// ── Toolbar wiring (expose to window) ───────────────────────────────────────

window.ideShowVersions = ideShowVersions;
window.ideSaveVersion  = ideSaveVersion;
window.ideRollback     = ideRollback;
window.ideShowGraph    = ideShowGraph;

// ── Bot Test ───────────────────────────────────────────────────────────────

async function ideTestBot(code, message) {
  if (!code) {
    const editor = window.ideEditor || document.querySelector('.ide-editor textarea');
    code = editor ? (editor.value || editor.textContent) : '';
  }
  if (!message) message = '/start';

  try {
    const res = await fetch('/api/ide/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + (localStorage.getItem('token') || '')
      },
      body: JSON.stringify({ code, message, update_type: message.startsWith('/') ? 'command' : 'message' })
    });
    const data = await res.json();

    let panel = document.getElementById('ide-test-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'ide-test-panel';
      panel.style.cssText = 'position:fixed;bottom:20px;right:20px;width:340px;background:var(--bg-secondary,#1e1e2e);border:1px solid var(--border-color,#333);border-radius:12px;padding:16px;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,.4);';
      document.body.appendChild(panel);
    }
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <strong style="color:var(--text-primary,#fff)">Test Result</strong>
        <button onclick="this.closest('#ide-test-panel').remove()" style="background:none;border:none;color:#aaa;cursor:pointer;font-size:18px">×</button>
      </div>
      <div style="color:${data.ok ? '#4ade80' : '#f87171'}">
        ${data.ok ? '✅ ' + (data.message || 'OK') : '❌ ' + (data.error || 'Error')}
      </div>
      ${data.details ? `<pre style="font-size:11px;color:#f87171;margin-top:8px;white-space:pre-wrap">${data.details}</pre>` : ''}
    `;
  } catch (e) {
    console.error('Test failed:', e);
  }
}

// ── Round-3: Current project ID helper ────────────────────────────────────

function ideGetCurrentProjectId() {
    // Prefer the private helper which derives a safe string from IDE.current.id
    if (typeof _ideProjectId === 'function') return _ideProjectId();
    return window._ideProjectId || localStorage.getItem('ide_current_project') || null;
}

// ── Round-3: Bot Metrics Panel ────────────────────────────────────────────

async function ideShowBotMetrics() {
    const projectId = ideGetCurrentProjectId();
    if (!projectId) return;

    const res = await fetch(`/api/ide/metrics/${projectId}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();

    const metricsHtml = Object.entries(data.metrics || {})
        .map(([k, v]) => `<div class="metric-row"><span>${k}</span><strong>${v}</strong></div>`)
        .join('') || '<p style="color:#888">No metrics yet</p>';

    const abHtml = Object.entries(data.ab_results || {})
        .map(([name, counts]) => {
            const [a, b] = Array.isArray(counts) ? counts : [counts.a || 0, counts.b || 0];
            const total = a + b;
            const pctA = total ? Math.round(a / total * 100) : 0;
            return `<div class="ab-row">
                <strong>${name}</strong>
                <div class="ab-bar">
                    <div style="width:${pctA}%;background:#4f8ef7">A: ${a} (${pctA}%)</div>
                    <div style="width:${100 - pctA}%;background:#e67e22">B: ${b} (${100 - pctA}%)</div>
                </div>
            </div>`;
        }).join('') || '';

    _ideShowModal('Bot Metrics', `
        <style>
            .metric-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a2a}
            .ab-bar{display:flex;height:20px;border-radius:4px;overflow:hidden;margin-top:4px}
            .ab-bar div{display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff}
            .ab-row{margin-bottom:12px}
        </style>
        <h4 style="color:#4f8ef7;margin:0 0 12px">Counters / Gauges</h4>
        ${metricsHtml}
        ${abHtml ? '<h4 style="color:#e67e22;margin:16px 0 8px">A/B Tests</h4>' + abHtml : ''}
    `);
}

// ── Round-3: AI Test Panel ─────────────────────────────────────────────────

async function ideTestAI(prompt) {
    const res = await fetch('/api/ide/ai/proxy', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Session-Token': localStorage.getItem('session_token') || ''
        },
        body: JSON.stringify({ prompt: prompt || 'Hello!' })
    });
    const data = await res.json();
    return data.text || data.error || 'No response';
}

// ── Round-4/8: Webhook Info Panel ───────────────────────────────────────────

async function ideShowWebhooks() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/webhooks/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const wh = data.webhooks || [];
    let html = '';
    if (Array.isArray(wh) && wh.length > 0) {
        for (const w of wh) {
            html += `<div style="border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:8px">
                <strong style="color:#4f8ef7">${w.path || '/'}</strong>
                <div style="color:#888;font-size:13px;margin-top:4px">Events: ${(w.events || []).join(', ') || 'all'}</div>
                <div style="color:#666;font-size:12px;margin-top:4px">URL: <code>/api/bot/webhook/${pid}${w.path}</code></div>
            </div>`;
        }
    } else {
        html = '<p style="color:#888">No webhooks defined. Add <code>webhook "/path" { ... }</code> to your script.</p>';
    }
    _ideShowModal('Webhooks', html);
}

// ── Queue Monitor Panel ────────────────────────────────────────────────────
async function ideShowQueues() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/queues/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const queues = data.queues || {};

    let html = '';
    for (const [name, info] of Object.entries(queues)) {
        const pending = info.pending || 0;
        const running = info.running || 0;
        const processed = info.processed || 0;
        const failed = info.failed || 0;
        html += `<div style="border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:8px">
            <strong style="color:#4f8ef7">${name}</strong>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px">
                <div><small style="color:#888">Pending</small><br><strong>${pending}</strong></div>
                <div><small style="color:#888">Running</small><br><strong style="color:#e67e22">${running}</strong></div>
                <div><small style="color:#888">Done</small><br><strong style="color:#2ecc71">${processed}</strong></div>
                <div><small style="color:#888">Failed</small><br><strong style="color:#e74c3c">${failed}</strong></div>
            </div>
        </div>`;
    }
    if (!html) html = '<p style="color:#888">No queues defined</p>';
    _ideShowModal('ide-queues-modal', html);
}

// ── Audit Log Panel ────────────────────────────────────────────────────────
async function ideShowAuditLog() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/audit/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const entries = data.entries || [];

    let html = entries.length ? '' : '<p style="color:#888">No audit entries yet</p>';
    for (const e of entries.reverse()) {
        const ts = new Date((e.timestamp || 0) * 1000).toLocaleString();
        html += `<div style="border-bottom:1px solid #2a2a2a;padding:8px 0">
            <strong style="color:#e67e22">${e.action || '?'}</strong>
            <span style="color:#666;font-size:12px;float:right">${ts}</span>
            <div style="color:#aaa;font-size:13px;margin-top:4px">${JSON.stringify(e.details || {})}</div>
        </div>`;
    }
    _ideShowModal('ide-audit-modal', `<div style="max-height:400px;overflow-y:auto">${html}</div>`);
}

window.ideGetCurrentProjectId = ideGetCurrentProjectId;
window.ideShowBotMetrics      = ideShowBotMetrics;
window.ideTestAI              = ideTestAI;
window.ideShowQueues          = ideShowQueues;
window.ideShowAuditLog        = ideShowAuditLog;

// ── Admin Panel Preview ────────────────────────────────────────────────────
async function ideShowAdminPanel() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/admin/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    if (!data.ok) {
        _ideShowModal('Admin Panel', '<p style="color:#888">No admin panel defined. Add <code>admin { ... }</code> to your .grav script.</p>');
        return;
    }
    const admin = data.admin;
    const title = admin.title || 'Bot Admin';
    const sections = admin.sections || [];

    let html = `<h3 style="color:#4f8ef7;margin:0 0 16px">${title}</h3>`;
    for (const sec of sections) {
        html += `<div style="border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:12px">
            <h4 style="margin:0 0 8px;color:#e67e22">${sec.name || 'Section'}</h4>`;
        if (sec.table && Array.isArray(sec.table)) {
            if (sec.table.length > 0) {
                const keys = Object.keys(sec.table[0]);
                html += '<table style="width:100%;border-collapse:collapse;font-size:13px">';
                html += '<tr>' + keys.map(k => `<th style="text-align:left;padding:4px 8px;border-bottom:1px solid #444;color:#888">${k}</th>`).join('') + '</tr>';
                for (const row of sec.table.slice(0, 20)) {
                    html += '<tr>' + keys.map(k => `<td style="padding:4px 8px;border-bottom:1px solid #2a2a2a">${row[k] ?? ''}</td>`).join('') + '</tr>';
                }
                html += '</table>';
            } else {
                html += '<p style="color:#888">No data</p>';
            }
        }
        if (sec.actions && Array.isArray(sec.actions)) {
            html += '<div style="margin-top:8px">' + sec.actions.map(a =>
                `<button style="background:#333;border:1px solid #555;color:#fff;padding:4px 12px;border-radius:4px;margin-right:4px;cursor:pointer">${a}</button>`
            ).join('') + '</div>';
        }
        html += '</div>';
    }
    _ideShowModal('Admin Panel', html);
}

// ── Middleware Info ─────────────────────────────────────────────────────────
function ideShowMiddlewareInfo() {
    _ideShowModal('Middleware', `
        <p style="color:#aaa">Define middleware in your .grav script:</p>
        <pre style="background:#1a1a2e;padding:12px;border-radius:6px;color:#98c379;margin:8px 0">middleware logging(ctx, next) {
    log("→ " + ctx.trigger)
    let result = next(ctx)
    log("← done")
    return result
}

use middleware logging</pre>
        <p style="color:#aaa;margin-top:12px">Middleware wraps all handler executions in order.</p>
    `);
}

window.ideShowAdminPanel    = ideShowAdminPanel;
window.ideShowMiddlewareInfo = ideShowMiddlewareInfo;

// ── Analytics Dashboard ────────────────────────────────────────────────────
async function ideShowAnalyticsDashboard() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/analytics/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const summary = data.summary || {};

    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:16px">';
    for (const [event, count] of Object.entries(summary)) {
        html += `<div style="background:#1a1a2e;border-radius:8px;padding:12px;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:#4f8ef7">${count}</div>
            <div style="font-size:12px;color:#888;margin-top:4px">${event}</div>
        </div>`;
    }
    html += '</div>';
    if (!Object.keys(summary).length) html = '<p style="color:#888">No analytics events yet. Use <code>track("event")</code> in your .grav script.</p>';
    _ideShowModal('Analytics', html);
}

// ── Package Manager ────────────────────────────────────────────────────────
async function ideShowPackages() {
    const res = await fetch('/api/ide/packages', {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const packages = data.packages || [];

    let html = packages.map(p => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #2a2a2a">
            <div>
                <strong style="color:#4f8ef7">${p.name}</strong> <span style="color:#666">v${p.version}</span>
                <div style="color:#888;font-size:13px">${p.description}</div>
            </div>
            <button onclick="ideInstallPackage('${p.name}')" style="background:#4f8ef7;border:none;color:#fff;padding:6px 16px;border-radius:4px;cursor:pointer;white-space:nowrap">Install</button>
        </div>
    `).join('');
    _ideShowModal('Packages', html);
}

async function ideInstallPackage(name) {
    const pid = ideGetCurrentProjectId();
    const res = await fetch('/api/ide/packages/install', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Session-Token': localStorage.getItem('session_token') || ''
        },
        body: JSON.stringify({ project_id: pid, package: name })
    });
    const data = await res.json();
    if (data.ok) {
        const t = document.createElement('div');
        t.textContent = `Installed ${name}`;
        t.style.cssText = 'position:fixed;top:20px;right:20px;background:#2ecc71;color:#fff;padding:10px 20px;border-radius:8px;z-index:99999;font-size:14px';
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 3000);
    }
}

// ── Circuit Breakers ───────────────────────────────────────────────────────
async function ideShowBreakers() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/breakers/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const breakers = data.breakers || {};

    let html = '';
    for (const [name, state] of Object.entries(breakers)) {
        const color = state.status === 'closed' ? '#2ecc71' : state.status === 'open' ? '#e74c3c' : '#e67e22';
        html += `<div style="border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <strong>${name}</strong>
                <span style="color:${color};font-weight:bold;text-transform:uppercase">${state.status || '?'}</span>
            </div>
            <div style="color:#888;font-size:13px;margin-top:4px">Failures: ${state.failures || 0} / ${state.threshold || '?'}</div>
        </div>`;
    }
    if (!html) html = '<p style="color:#888">No circuit breakers defined</p>';
    _ideShowModal('Circuit Breakers', html);
}

window.ideShowAnalyticsDashboard = ideShowAnalyticsDashboard;
window.ideShowPackages = ideShowPackages;
window.ideInstallPackage = ideInstallPackage;
window.ideShowBreakers = ideShowBreakers;

// ── Form Preview ──────────────────────────────────────────────────────────
function idePreviewForm(config) {
    let html = '<form onsubmit="return false" style="display:flex;flex-direction:column;gap:12px">';
    for (const f of (config.fields || [])) {
        html += `<div><label style="color:#888;font-size:13px;display:block;margin-bottom:4px">${f.name}${f.required ? ' *' : ''}</label>`;
        if (f.kind === 'textarea') {
            html += `<textarea style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:8px;border-radius:4px;min-height:60px" name="${f.name}"></textarea>`;
        } else if (f.kind === 'select') {
            html += `<select style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:8px;border-radius:4px" name="${f.name}">` +
                (f.options || []).map(o => `<option>${o}</option>`).join('') + '</select>';
        } else if (f.kind === 'rating') {
            html += `<div style="display:flex;gap:4px">${Array.from({length: f.max || 5}, (_, i) => `<button style="background:#333;border:1px solid #555;color:#fff;width:32px;height:32px;border-radius:4px;cursor:pointer">${i + 1}</button>`).join('')}</div>`;
        } else {
            html += `<input type="text" style="width:100%;background:#1a1a2e;border:1px solid #333;color:#fff;padding:8px;border-radius:4px" name="${f.name}"/>`;
        }
        html += '</div>';
    }
    html += `<button style="background:#4f8ef7;border:none;color:#fff;padding:10px;border-radius:6px;cursor:pointer;font-size:14px;margin-top:8px">${config.submit || 'Submit'}</button>`;
    html += '</form>';
    _ideShowModal('Form Preview', html);
}

// ── Permissions Panel ─────────────────────────────────────────────────────
async function ideShowPermissions() {
    const pid = ideGetCurrentProjectId();
    if (!pid) return;
    const res = await fetch(`/api/ide/permissions/${pid}`, {
        headers: {'X-Session-Token': localStorage.getItem('session_token') || ''}
    });
    const data = await res.json();
    const perms = data.permissions;
    if (!perms) {
        _ideShowModal('Permissions', '<p style="color:#888">No permissions defined. Add <code>permissions { ... }</code> to your script.</p>');
        return;
    }
    let html = `<div style="margin-bottom:12px;color:#888">Default role: <strong style="color:#e67e22">${perms.default || 'user'}</strong></div>`;
    for (const [role, abilities] of Object.entries(perms.roles || {})) {
        html += `<div style="border:1px solid #333;border-radius:8px;padding:10px;margin-bottom:8px">
            <strong style="color:#2ecc71">${role}</strong>
            <div style="color:#888;font-size:13px;margin-top:4px">${(abilities || []).join(', ')}</div>
        </div>`;
    }
    _ideShowModal('Permissions (RBAC)', html);
}

window.idePreviewForm = idePreviewForm;
window.ideShowWebhooks = ideShowWebhooks;
window.ideShowPermissions = ideShowPermissions;
