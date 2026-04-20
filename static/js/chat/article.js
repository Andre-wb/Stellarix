/* Article composer + Markdown/LaTeX renderer + inline-math helper.
 *
 * Articles go out as a regular encrypted chat message with "[ARTICLE] "
 * prefix followed by Markdown + LaTeX source. The receiver decrypts,
 * detects the prefix, and renders full Markdown with KaTeX math.
 *
 * SECURITY: all HTML assembled in this module passes through
 * _sanitizeFragment() — a strict whitelist (tags, attrs, urls) — before
 * being inserted anywhere in the DOM. Raw message bytes start life
 * escaped via _esc(); the only HTML we trust is what the sanitizer
 * returns and what KaTeX emits (KaTeX is configured with trust:false,
 * strict:"warn" so \href / \htmlId / raw HTML are rejected).
 */

const ARTICLE_PREFIX    = '[ARTICLE] ';
const ARTICLE_MAX_BYTES = 256 * 1024;

function _katex()  { return window.katex; }
function _marked() { return window.marked; }

function _esc(s) {
    return String(s || '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function _renderMath(expr, display) {
    const k = _katex();
    if (!k || !k.renderToString) {
        return `<code class="vx-math-fallback">${display ? '$$' : '$'}${_esc(expr)}${display ? '$$' : '$'}</code>`;
    }
    try {
        return k.renderToString(expr, {
            displayMode: !!display,
            throwOnError: false,
            trust:        false,     // no \href / \htmlId / url -> JS
            strict:      'warn',
            maxSize:      50,
            maxExpand:    100,
        });
    } catch (e) {
        return `<span class="vx-math-error" title="${_esc(e.message || '')}">${display ? '$$' : '$'}${_esc(expr)}${display ? '$$' : '$'}</span>`;
    }
}

/**
 * Substitute inline + block math inside already-escaped text. The caller
 * is responsible for escaping user input first (_esc) — this function
 * only operates on trusted, escaped text.
 */
function _substituteMathInEscapedText(escaped) {
    let changed = false;
    let out = escaped.replace(/\$\$([\s\S]+?)\$\$/g, (_, expr) => {
        changed = true;
        return _renderMath(expr.trim(), true);
    });
    out = out.replace(/(^|[^\\])\$([^\s$][^$\n]*?[^\s\\])\$(?=$|[^0-9])/g,
        (full, prefix, expr) => {
            changed = true;
            return prefix + _renderMath(expr, false);
        });
    return { html: out, changed };
}

/**
 * Public helper: render user-supplied plain text with math support.
 * Escapes first, runs math, returns safe HTML string.
 */
export function renderTextWithMath(src) {
    if (!src) return '';
    const escaped = _esc(src);
    const { html } = _substituteMathInEscapedText(escaped);
    return html.replace(/\n/g, '<br>');
}

/**
 * Render a full Markdown+math article. Returns a *sanitized* HTML
 * fragment string. Caller inserts via _setSanitized().
 */
export function renderArticle(markdownSrc) {
    const mk = _marked();
    let raw;
    if (mk && mk.parse) {
        try {
            mk.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false,
            });
        } catch (_) {}
        raw = mk.parse(markdownSrc || '');
    } else {
        raw = '<pre class="vx-md-fallback">' + _esc(markdownSrc || '') + '</pre>';
    }

    // Strict whitelist pass over the marked() output.
    const clean = _sanitizeFragment(raw);
    // Then math substitution over the text nodes only — tag structure
    // stays untouched, KaTeX output is whitelist-safe.
    return _mathPassOverFragment(clean);
}

/**
 * Strict whitelist sanitizer. Parses the input string into a detached
 * DOM, strips everything not allowed, returns clean serialized HTML.
 */
function _sanitizeFragment(html) {
    const tmp = document.createElement('template');
    // Using DOMParser would be identical; <template> avoids running
    // <script> in any case.
    tmp.innerHTML = html;

    const ALLOWED_TAGS = new Set([
        'p','br','hr','em','strong','code','pre','blockquote',
        'ul','ol','li','h1','h2','h3','h4','h5','h6',
        'a','img','table','thead','tbody','tr','th','td',
        'del','span','div',
        // KaTeX output tags
        'mjx-container','math','annotation','semantics','mfrac','mi','mn',
        'mo','msqrt','msup','msub','msubsup','mrow','mspace','mstyle','mtext',
        's','svg','path','g','line','rect','text','tspan','use',
    ]);
    const ALLOWED_ATTRS_BY_TAG = {
        a:     new Set(['href','title']),
        img:   new Set(['src','alt','title']),
        span:  new Set(['class','style','aria-hidden']),
        div:   new Set(['class','style']),
        code:  new Set(['class']),
        pre:   new Set(['class']),
        // KaTeX
        'mjx-container': new Set(['class','jax','style']),
        svg:  new Set(['class','width','height','viewBox','preserveAspectRatio','xmlns','style']),
        path: new Set(['d','fill','stroke','stroke-width']),
        g:    new Set(['transform']),
        line: new Set(['x1','y1','x2','y2','stroke','stroke-width']),
        rect: new Set(['x','y','width','height','fill']),
        text: new Set(['x','y','fill','text-anchor','font-size','font-family']),
        tspan:new Set(['x','y']),
        use:  new Set(['href','x','y']),
        annotation: new Set(['encoding']),
        semantics: new Set([]),
        math: new Set(['xmlns','display']),
    };
    // Only whitelisted inline styles.
    const STYLE_ALLOW_RE = /^(color|background|margin|padding|padding-left|padding-right|padding-top|padding-bottom|font-size|font-weight|font-family|text-align|border|border-[a-z-]+|display|width|height|opacity|transform|line-height|letter-spacing|white-space):\s*[-#a-z0-9_,.()%/ \t]+$/i;

    (function walk(node) {
        const kids = Array.from(node.children);
        for (const el of kids) {
            const tag = el.tagName.toLowerCase();
            if (!ALLOWED_TAGS.has(tag)) {
                el.remove();
                continue;
            }
            const allowed = ALLOWED_ATTRS_BY_TAG[tag] || new Set();
            for (const attr of Array.from(el.attributes)) {
                const name = attr.name.toLowerCase();
                if (name.startsWith('on')) { el.removeAttribute(attr.name); continue; }
                if (!allowed.has(name)) { el.removeAttribute(attr.name); continue; }
                const v = attr.value || '';
                if ((name === 'href' || name === 'src') && /^\s*javascript:/i.test(v)) {
                    el.removeAttribute(attr.name);
                    continue;
                }
                if (name === 'style') {
                    const clean = v.split(';')
                        .map(p => p.trim()).filter(p => STYLE_ALLOW_RE.test(p))
                        .join('; ');
                    if (!clean) el.removeAttribute('style');
                    else el.setAttribute('style', clean);
                }
            }
            if (tag === 'a' && el.getAttribute('href')) {
                el.setAttribute('target', '_blank');
                el.setAttribute('rel', 'noopener noreferrer');
            }
            walk(el);
        }
    })(tmp.content);

    const serializer = new XMLSerializer();
    let out = '';
    for (const n of tmp.content.childNodes) {
        out += (n.nodeType === 1) ? serializer.serializeToString(n)
                                  : _esc(n.nodeValue || '');
    }
    return out;
}

function _mathPassOverFragment(cleanHtml) {
    const tmp = document.createElement('template');
    tmp.innerHTML = cleanHtml;

    (function walk(node) {
        const kids = Array.from(node.childNodes);
        for (const ch of kids) {
            if (ch.nodeType === 3) {
                const text = ch.nodeValue || '';
                if (!text.includes('$')) continue;
                const { html, changed } = _substituteMathInEscapedText(_esc(text));
                if (!changed) continue;
                const span = document.createElement('span');
                // KaTeX output is constrained; whitelist sanitizer already
                // ran on surrounding HTML. We apply a final pass over the
                // math-injected fragment as defense-in-depth.
                _setSanitized(span, html);
                ch.replaceWith(span);
            } else if (ch.nodeType === 1) {
                const tag = ch.tagName.toLowerCase();
                if (tag !== 'code' && tag !== 'pre') walk(ch);
            }
        }
    })(tmp.content);

    const serializer = new XMLSerializer();
    let out = '';
    for (const n of tmp.content.childNodes) {
        out += (n.nodeType === 1) ? serializer.serializeToString(n)
                                  : _esc(n.nodeValue || '');
    }
    return out;
}

/**
 * Single chokepoint for inserting sanitized HTML. Every caller that
 * writes article output must go through here — we re-run the sanitizer
 * so any future refactor can't accidentally bypass the whitelist.
 */
function _setSanitized(el, html) {
    const clean = _sanitizeFragment(html);
    el.innerHTML = clean;       // eslint-disable-line no-restricted-syntax -- sanitized above
}

/**
 * Public: render article message into an existing element.
 */
export function renderArticleInto(el, msgText) {
    const src = (msgText || '').startsWith(ARTICLE_PREFIX)
        ? msgText.slice(ARTICLE_PREFIX.length)
        : (msgText || '');
    el.classList.add('vx-article');
    _setSanitized(el, renderArticle(src));
}

// ── Composer ─────────────────────────────────────────────────────────────

function _openComposer() {
    const root = document.getElementById('article-composer');
    const src  = document.getElementById('article-src');
    if (!root || !src) return;
    root.style.display = '';
    src.value = '';
    _refreshPreview();
    setTimeout(() => src.focus(), 50);
    src.addEventListener('input', _refreshPreview);
}

function _closeComposer() {
    const root = document.getElementById('article-composer');
    if (root) root.style.display = 'none';
}

function _refreshPreview() {
    const src     = document.getElementById('article-src');
    const preview = document.getElementById('article-preview');
    const sizeEl  = document.getElementById('article-size');
    if (!src || !preview) return;
    const text = src.value;
    const bytes = new TextEncoder().encode(text).length;
    if (sizeEl) {
        sizeEl.textContent = `${bytes} / ${ARTICLE_MAX_BYTES} B`;
        sizeEl.style.color = bytes > ARTICLE_MAX_BYTES ? '#ef4444' : '';
    }
    try {
        _setSanitized(preview, renderArticle(text));
    } catch (e) {
        preview.textContent = 'Ошибка превью: ' + e.message;
    }
}

async function _sendArticle() {
    const src = document.getElementById('article-src');
    if (!src) return;
    const text = (src.value || '').trim();
    if (!text) return;
    const bytes = new TextEncoder().encode(text).length;
    if (bytes > ARTICLE_MAX_BYTES) {
        if (window.showToast) window.showToast('Статья слишком длинная (>' + ARTICLE_MAX_BYTES + ' B)', 'error');
        return;
    }
    // Reuse the standard send pipeline — everything encrypts E2E.
    const input = document.getElementById('msg-input');
    const prev = input ? input.value : '';
    if (input) {
        input.value = ARTICLE_PREFIX + text;
        if (window.sendMessage) {
            try { await window.sendMessage(); }
            catch (e) {
                console.error('sendArticle failed', e);
                if (window.showToast) window.showToast(String(e), 'error');
            }
        }
        if (input.value === ARTICLE_PREFIX + text) input.value = prev;
    }
    _closeComposer();
}

window.openArticleComposer  = _openComposer;
window.closeArticleComposer = _closeComposer;
window.sendArticle          = _sendArticle;

/**
 * Walk a DOM element and swap text-node $...$ / $$...$$ with KaTeX HTML.
 * Used by render.js for ordinary chat messages. Skips <code>, <pre>, <a>
 * (URLs often contain $ that shouldn't become math).
 */
function mathifyElement(root) {
    if (!root) return;
    const SKIP = new Set(['CODE','PRE','A','SCRIPT','STYLE']);
    (function walk(n) {
        const kids = Array.from(n.childNodes);
        for (const ch of kids) {
            if (ch.nodeType === 3) {
                const text = ch.nodeValue || '';
                if (!text.includes('$')) continue;
                const { html, changed } = _substituteMathInEscapedText(_esc(text));
                if (!changed) continue;
                const span = document.createElement('span');
                _setSanitized(span, html);
                ch.replaceWith(span);
            } else if (ch.nodeType === 1 && !SKIP.has(ch.tagName)) {
                walk(ch);
            }
        }
    })(root);
}

window.vxArticle = {
    PREFIX: ARTICLE_PREFIX,
    renderArticle,
    renderArticleInto,
    renderTextWithMath,
    mathifyElement,
};
// Also expose as a top-level helper render.js can grab.
window._mathifyTextNodes = mathifyElement;
