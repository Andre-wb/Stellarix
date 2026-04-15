/* ── Minimal Markdown → HTML converter for translated docs ── */
function _mdToHtml(md) {
    if (!md) return '';
    const _esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    let html = '';
    let inCode = false;
    let codeLines = [];

    const lines = md.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Code blocks
        if (line.trim().startsWith('```')) {
            if (inCode) {
                html += '<pre class="gxd-code-raw">' + _esc(codeLines.join('\n')) + '</pre>';
                codeLines = [];
                inCode = false;
            } else {
                inCode = true;
            }
            continue;
        }
        if (inCode) { codeLines.push(line); continue; }

        const trimmed = line.trim();
        if (!trimmed) { html += '<br>'; continue; }
        if (trimmed === '---') { html += '<hr>'; continue; }

        // Headings
        if (trimmed.startsWith('### ')) { html += '<h3>' + _esc(trimmed.slice(4)) + '</h3>'; continue; }
        if (trimmed.startsWith('## '))  { html += '<h2>' + _esc(trimmed.slice(3)) + '</h2>'; continue; }
        if (trimmed.startsWith('# '))   { html += '<h1>' + _esc(trimmed.slice(2)) + '</h1>'; continue; }

        // Callouts: > **emoji text**
        if (trimmed.startsWith('> ')) {
            html += '<div class="gxd-callout gxd-callout-blue"><p>' + _esc(trimmed.slice(2)) + '</p></div>';
            continue;
        }

        // List items
        if (trimmed.startsWith('- ')) {
            html += '<li>' + _esc(trimmed.slice(2)) + '</li>';
            continue;
        }

        // Table rows
        if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
            if (trimmed.match(/^\|[\s\-|]+\|$/)) continue; // separator
            const cells = trimmed.slice(1, -1).split('|').map(c => '<td>' + _esc(c.trim()) + '</td>');
            html += '<tr>' + cells.join('') + '</tr>';
            continue;
        }

        // Normal paragraph
        html += '<p>' + _esc(trimmed) + '</p>';
    }
    // Close unclosed code block
    if (inCode && codeLines.length) {
        html += '<pre class="gxd-code-raw">' + _esc(codeLines.join('\n')) + '</pre>';
    }
    return html;
}

/* ── Build fullscreen docs overlay ───────────────────────── */
function _destroyDocsOverlay() {
    const el = document.getElementById('gx-docs-fs');
    if (el) el.remove();
}

function _buildDocsOverlay() {
    if (document.getElementById('gx-docs-fs')) return;

    const overlay = document.createElement('div');
    overlay.id = 'gx-docs-fs';
    overlay.className = 'gx-docs-fs';
    overlay.innerHTML = _buildDocsHTML();
    document.body.appendChild(overlay);

    // Highlight code blocks
    requestAnimationFrame(() => {
        overlay.querySelectorAll('.gxd-code-raw').forEach(el => {
            const raw = el.textContent;
            if (window._highlightGravitix) {
                el.innerHTML = window._highlightGravitix(raw);
            }
            el.classList.replace('gxd-code-raw', 'gxd-code-hl');
        });
        // TOC scroll spy
        _initScrollSpy();
    });

    // Close on Escape
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && overlay.classList.contains('open')) gxDocsClose();
    });
}

function _buildDocsHTML() {
    // TOC
    let tocHTML = '';
    GX_TOC.forEach(item => {
        if (item.group) {
            const groupText = _t(item.group, item.fallback || item.group);
            tocHTML += '<div class="gxd-toc-group">' + groupText + '</div>';
        } else {
            const label = item.i18n ? _t(item.i18n, item.label) : item.label;
            tocHTML += '<a class="gxd-toc-link" href="#gxs-' + item.id + '" data-section="' + item.id + '" onclick="gxDocsSectionClick(event,\'' + item.id + '\')">' + item.icon + ' ' + label + '</a>';
        }
    });

    // Content — built dynamically with _t() calls for i18n.
    // Code examples stay in Gravitix syntax (not translated).
    // Descriptions, headings, callouts, and code comments are translated.
    const sections = _gxSections();
    let contentHTML = '';
    GX_TOC.filter(t => t.id).forEach(item => {
        const html = sections[item.id] || '';
        contentHTML += '<section class="gxd-section" id="gxs-' + item.id + '">' + html + '</section>';
    });

    return `
    <div class="gxd-topbar">
      <div class="gxd-topbar-left">
        <button class="gxd-menu-btn" onclick="gxDocsMobileMenu()" title="Toggle menu">
          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>
        </button>
        <div class="gxd-topbar-logo">
          <span class="gxd-logo-gx">GX</span>
          <span class="gxd-topbar-title">${_t('gravitixDocs.title', 'Gravitix Language Reference')}</span>
          <span class="gxd-ver-badge">v1.0</span>
        </div>
      </div>
      <div class="gxd-topbar-center">
        <div class="gxd-search-wrap">
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14"/></svg>
          <input type="text" class="gxd-search-input" id="gxd-search" placeholder="${_t('app.search', 'Search the docs...')}" oninput="gxDocsSearch(this.value)">
        </div>
      </div>
      <div class="gxd-topbar-right">
        <button class="gxd-close-btn" onclick="gxDocsClose()" title="Close docs">
          <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
    </div>
    <div class="gxd-body">
      <nav class="gxd-toc" id="gxd-toc">${tocHTML}</nav>
      <main class="gxd-main" id="gxd-main">
        <div class="gxd-content" id="gxd-content">
          ${contentHTML}
        </div>
        <div id="gxd-no-results" class="gxd-no-results" style="display:none;">
          <div class="gxd-no-results-icon">🔍</div>
          <div>${_t('app.noResults', 'No results found')}</div>
        </div>
      </main>
    </div>`;
}

/* ── Scroll spy ──────────────────────────────────────────── */
function _initScrollSpy() {
    const main = document.getElementById('gxd-main');
    if (!main) return;
    const sections = document.querySelectorAll('.gxd-section');
    const links = document.querySelectorAll('.gxd-toc-link');
    const obs = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (e.isIntersecting) {
                const id = e.target.id.replace('gxs-', '');
                links.forEach(l => l.classList.toggle('active', l.dataset.section === id));
                // Scroll TOC link into view
                const active = document.querySelector(`.gxd-toc-link[data-section="${id}"]`);
                if (active) active.scrollIntoView({ block: 'nearest' });
            }
        });
    }, { root: main, threshold: 0.15 });
    sections.forEach(s => obs.observe(s));
}

/* ── Public API ──────────────────────────────────────────── */
function gxDocsOpen() {
    _buildDocsOverlay();
    const el = document.getElementById('gx-docs-fs');
    if (el) {
        el.classList.add('open');
        document.body.style.overflow = 'hidden';
        // Reset search
        const si = document.getElementById('gxd-search');
        if (si) { si.value = ''; gxDocsSearch(''); }
    }
}

function gxDocsClose() {
    const el = document.getElementById('gx-docs-fs');
    if (el) el.classList.remove('open');
    document.body.style.overflow = '';
}

function gxDocsSectionClick(e, id) {
    e.preventDefault();
    const target = document.getElementById('gxs-' + id);
    const main = document.getElementById('gxd-main');
    if (target && main) {
        main.scrollTo({ top: target.offsetTop - 16, behavior: 'smooth' });
    }
    // Close mobile menu
    document.getElementById('gxd-toc')?.classList.remove('mobile-open');
}

function gxDocsMobileMenu() {
    document.getElementById('gxd-toc')?.classList.toggle('mobile-open');
}

function gxDocsSearch(q) {
    const sections = document.querySelectorAll('.gxd-section');
    const noRes = document.getElementById('gxd-no-results');
    let found = 0;
    const lq = q.toLowerCase();
    sections.forEach(s => {
        const match = !lq || s.textContent.toLowerCase().includes(lq);
        s.style.display = match ? '' : 'none';
        if (match) found++;
    });
    if (noRes) noRes.style.display = (q && found === 0) ? '' : 'none';
}

/* ── Override old ideToggleDocs ──────────────────────────── */
window.ideToggleDocs = function() {
    const el = document.getElementById('gx-docs-fs');
    if (el && el.classList.contains('open')) {
        gxDocsClose();
    } else {
        gxDocsOpen();
    }
};

window.gxDocsOpen         = gxDocsOpen;
window.gxDocsClose        = gxDocsClose;
window.gxDocsSectionClick = gxDocsSectionClick;
window.gxDocsMobileMenu   = gxDocsMobileMenu;
window.gxDocsSearch       = gxDocsSearch;

/* ── Rebuild docs when language changes ─────────────────── */
window.gxDocsRebuild = function() {
    const wasOpen = document.getElementById('gx-docs-fs')?.classList.contains('open');
    _destroyDocsOverlay();
    if (wasOpen) gxDocsOpen();
};
