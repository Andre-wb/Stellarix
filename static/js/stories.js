// static/js/stories.js — E2E Encrypted Stories (Instagram/Telegram style)
import { api, esc } from './utils.js';
import {
    generateStoryKey, storyEncrypt, storyDecryptText,
    storyEncryptBlob, storyDecryptBlob,
    wrapStoryKeyForContacts, unwrapStoryKey,
    eciesEncrypt,
} from './crypto.js';

// ── State ────────────────────────────────────────────────────────────────────
let _groups = [];          // story groups from API
let _gi = 0;               // current group index
let _si = 0;               // story index within group
let _progress = 0;         // 0..100
let _raf = null;           // requestAnimationFrame handle
let _lastTs = null;        // last frame timestamp
let _paused = false;
let _holdTimer = null;     // long-press detect timer
let _camStream = null;     // camera MediaStream
let _camRecorder = null;
let _camChunks = [];
let _isRecording = false;
let _scType = null;        // current creator type
let _scFile = null;        // selected media File
let _scMusicFile = null;
let _scTextColor = '#ffffff';
let _scBg = 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)';
let _expanded = false;     // stories strip expanded state

// ── Public: set of user IDs that have active stories ─────────────────────────
export const storyUserIds = new Set();

// ── Load & render strip ───────────────────────────────────────────────────────
export async function loadStories() {
    try {
        const data = await api('GET', '/api/stories');
        _groups = data.story_groups || [];
    } catch {
        _groups = [];
    }
    storyUserIds.clear();
    for (const g of _groups) {
        if (g.user_id && g.stories?.length) storyUserIds.add(g.user_id);
    }
    _sortGroups();
    renderStoriesStrip();
}

export function renderStoriesStrip() {
    const track = document.getElementById('stories-track');
    if (!track) return;

    const S = window.AppState;
    const myId = S.user?.id;

    // Always show "Add story" (self) first
    let html = '';

    // Self bubble: если есть истории → открыть просмотр, иначе → создать
    const selfGroup = _groups.find(g => g.is_self);
    const selfIdx = selfGroup ? _groups.indexOf(selfGroup) : -1;
    const selfAction = selfGroup && selfGroup.stories.length > 0
        ? `window.openStories(${selfIdx})`
        : `window.showStoryCreator()`;
    html += `<button class="st-bubble st-self" onclick="${selfAction}" title="${window.t ? window.t('stories.myStory') : 'My Story'}">
        <div class="st-ring ${selfGroup && selfGroup.stories.length > 0 ? 'has-story' : ''}">
            <div class="st-avatar">${_avatarHtml(S.user?.avatar_url, S.user?.avatar_emoji || '👤')}</div>
            ${!selfGroup || selfGroup.stories.length === 0 ? '<div class="st-add-badge">+</div>' : ''}
        </div>
        <span class="st-label">${window.t ? window.t('stories.myStory') : 'My'}</span>
    </button>`;

    // Other users
    const others = _groups.filter(g => !g.is_self);
    const visible = _expanded ? others : others.slice(0, 3);

    for (const g of visible) {
        const idx = _groups.indexOf(g);
        html += `<button class="st-bubble" onclick="window.openStories(${idx})" title="${esc(g.display_name)}">
            <div class="st-ring${g.has_unseen !== false ? ' unseen' : ''}">
                <div class="st-avatar">${_avatarHtml(g.avatar_url, g.avatar_emoji || '👤')}</div>
            </div>
            <span class="st-label">${esc(g.display_name.split(' ')[0])}</span>
        </button>`;
    }

    // Show-all / collapse toggle
    if (others.length > 3) {
        if (!_expanded) {
            const showMoreLabel = window.t ? window.t('stories.showMore').replace('{n}', others.length - 3) : `+${others.length - 3}`;
            html += `<button class="st-bubble" onclick="window.expandStories()" title="${window.t ? window.t('stories.showAll') : 'Show all'}">
                <div class="st-ring" style="background:var(--bg3);">
                    <div class="st-avatar" style="display:flex;align-items:center;justify-content:center;font-size:18px;">›</div>
                </div>
                <span class="st-label">${showMoreLabel}</span>
            </button>`;
        } else {
            html += `<button class="st-bubble" onclick="window.collapseStories()" title="${window.t ? window.t('stories.collapse') : 'Collapse'}">
                <div class="st-ring" style="background:var(--bg3);">
                    <div class="st-avatar" style="display:flex;align-items:center;justify-content:center;font-size:18px;">‹</div>
                </div>
                <span class="st-label">${window.t ? window.t('stories.collapse') : 'Collapse'}</span>
            </button>`;
        }
    }

    track.innerHTML = html;

    const strip = document.getElementById('stories-strip');
    if (strip) strip.style.display = '';
}

function _avatarHtml(url, emoji) {
    if (url) return `<img src="${esc(url)}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
    return `<span style="font-size:20px;">${esc(emoji)}</span>`;
}

export function expandStories() { _expanded = true; renderStoriesStrip(); }
export function collapseStories() { _expanded = false; renderStoriesStrip(); }

// ── Viewer ────────────────────────────────────────────────────────────────────
export function openStories(groupIdx) {
    if (!_groups.length) return;
    _gi = Math.max(0, Math.min(groupIdx, _groups.length - 1));
    _si = 0;
    _paused = false;
    const viewer = document.getElementById('story-viewer');
    if (!viewer) return;
    viewer.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    _renderCurrent();
    _startProgress();
    // Mark viewed
    _markViewed();
}

export function closeStoryViewer() {
    _stopProgress();
    const viewer = document.getElementById('story-viewer');
    if (viewer) viewer.style.display = 'none';
    document.body.style.overflow = '';
    // Stop video/audio
    const vid = document.getElementById('sv-video');
    if (vid) { vid.pause(); vid.src = ''; }
    const aud = document.getElementById('sv-audio');
    if (aud) { aud.pause(); aud.src = ''; }
    _stopCamera();
}

async function _renderCurrent() {
    const group = _groups[_gi];
    if (!group) { closeStoryViewer(); return; }
    const story = group.stories[_si];
    if (!story) { closeStoryViewer(); return; }

    const S = window.AppState;

    // User info
    document.getElementById('sv-username').textContent = group.display_name;
    document.getElementById('sv-time').textContent = _timeAgo(story.created_at);
    const avatarEl = document.getElementById('sv-avatar');
    // Safe avatar rendering using DOM methods
    avatarEl.textContent = '';
    if (group.avatar_url) {
        const avatarImg = document.createElement('img');
        avatarImg.src = group.avatar_url;
        avatarImg.style.cssText = 'width:40px;height:40px;border-radius:50%;object-fit:cover;';
        avatarEl.appendChild(avatarImg);
    } else {
        avatarEl.textContent = group.avatar_emoji || '\u{1F464}';
    }

    // Add + Delete buttons for own stories
    const addBtn = document.getElementById('sv-add-btn');
    if (addBtn) addBtn.style.display = group.is_self ? 'flex' : 'none';
    const delBtn = document.getElementById('sv-delete-btn');
    if (delBtn) delBtn.style.display = group.is_self ? 'flex' : 'none';

    // Views counter (own stories) / Actions bar (other's stories)
    const viewsEl = document.getElementById('sv-views');
    const viewsCount = document.getElementById('sv-views-count');
    const actionsEl = document.getElementById('sv-actions');
    if (group.is_self) {
        if (viewsEl) { viewsEl.style.display = 'flex'; }
        viewsCount.textContent = story.views_count || 0;
        if (actionsEl) actionsEl.style.display = 'none';
    } else {
        if (viewsEl) viewsEl.style.display = 'none';
        if (actionsEl) actionsEl.style.display = 'flex';
    }

    // Media
    const img = document.getElementById('sv-img');
    const vid = document.getElementById('sv-video');
    const textSlide = document.getElementById('sv-text-slide');
    const content = document.getElementById('sv-content');

    img.style.display = 'none';
    vid.style.display = 'none';
    textSlide.style.display = 'none';

    // ── E2E Decryption ──────────────────────────────────────────────
    let storyKey = null;
    let decryptedText = '';
    let meta = { text_color: '#ffffff', bg_color: 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)', music_title: '' };

    if (story.encrypted && story.key_envelope) {
        try {
            const privJwk = localStorage.getItem('vortex_x25519');
            if (privJwk) {
                storyKey = await unwrapStoryKey(story.key_envelope, privJwk);
            }
        } catch (e) {
            console.warn('[STORY] Failed to unwrap story key:', e);
        }

        if (storyKey) {
            if (story.text_ct) {
                try { decryptedText = await storyDecryptText(story.text_ct, storyKey); } catch {}
            }
            if (story.meta_ct) {
                try {
                    const metaJson = await storyDecryptText(story.meta_ct, storyKey);
                    meta = { ...meta, ...JSON.parse(metaJson) };
                } catch {}
            }
        }
    } else if (!story.encrypted) {
        decryptedText = story.text || '';
        meta = { text_color: story.text_color || '#fff', bg_color: story.bg_color || meta.bg_color, music_title: story.music_title || '' };
    }

    // Render media
    if (story.encrypted && storyKey && story.has_media) {
        try {
            const resp = await fetch(`/api/stories/${story.id}/media`, { credentials: 'include' });
            if (resp.ok) {
                const encBuf = await resp.arrayBuffer();
                const plainBuf = await storyDecryptBlob(encBuf, storyKey);
                const blob = new Blob([plainBuf]);
                const url = URL.createObjectURL(blob);

                if (story.media_type === 'photo') {
                    img.src = url;
                    img.style.display = 'block';
                    img.onload = () => URL.revokeObjectURL(url);
                    content.style.background = '#000';
                } else if (story.media_type === 'video') {
                    vid.src = url;
                    vid.style.display = 'block';
                    vid.muted = false;
                    vid.play().catch(() => {});
                    vid.onended = () => URL.revokeObjectURL(url);
                    content.style.background = '#000';
                }
            }
        } catch (e) {
            console.warn('[STORY] Failed to decrypt media:', e);
        }
    } else if (!story.encrypted && story.media_url) {
        if (story.media_type === 'photo') {
            img.src = story.media_url;
            img.style.display = 'block';
            content.style.background = '#000';
        } else if (story.media_type === 'video') {
            vid.src = story.media_url;
            vid.style.display = 'block';
            vid.muted = false;
            vid.play().catch(() => {});
            content.style.background = '#000';
        }
    }

    if (story.media_type === 'text' || (!story.has_media && !story.media_url)) {
        textSlide.style.display = 'flex';
        textSlide.style.background = meta.bg_color;
        const p = document.getElementById('sv-text-content');
        p.textContent = decryptedText;
        p.style.color = meta.text_color || '#fff';
        content.style.background = 'transparent';
    }

    // Music
    const musicBadge = document.getElementById('sv-music-badge');
    const audio = document.getElementById('sv-audio');

    if (story.encrypted && storyKey && story.has_music) {
        try {
            const resp = await fetch(`/api/stories/${story.id}/music`, { credentials: 'include' });
            if (resp.ok) {
                const encBuf = await resp.arrayBuffer();
                const plainBuf = await storyDecryptBlob(encBuf, storyKey);
                const blob = new Blob([plainBuf]);
                audio.src = URL.createObjectURL(blob);
                audio.play().catch(() => {});
                musicBadge.style.display = 'flex';
                document.getElementById('sv-music-title').textContent = meta.music_title || '\u266B';
            }
        } catch {}
    } else if (!story.encrypted && (story.music_url || story.music_title)) {
        musicBadge.style.display = 'flex';
        document.getElementById('sv-music-title').textContent = story.music_title || '\u266B';
        if (story.music_url) {
            audio.src = story.music_url;
            audio.play().catch(() => {});
        }
    } else {
        musicBadge.style.display = 'none';
        audio.pause();
        audio.src = '';
    }

    // Progress bars
    _buildProgressBars(group.stories.length);
}

function _buildProgressBars(count) {
    const row = document.getElementById('sv-progress-row');
    if (!row) return;
    let html = '';
    for (let i = 0; i < count; i++) {
        const pct = i < _si ? 100 : (i === _si ? 0 : 0);
        html += `<div class="sv-prog-bar"><div class="sv-prog-fill" id="sv-prog-${i}" style="width:${pct}%"></div></div>`;
    }
    row.innerHTML = html;
}

function _startProgress() {
    _stopProgress();
    _progress = 0;
    _lastTs = null;
    const group = _groups[_gi];
    if (!group) return;
    const story = group.stories[_si];
    const dur = (story?.media_type === 'video' ? (story.duration || 15) : (story?.duration || 5)) * 1000;

    const animate = (ts) => {
        if (_paused) { _raf = requestAnimationFrame(animate); return; }
        if (_lastTs === null) _lastTs = ts;
        const delta = ts - _lastTs;
        _lastTs = ts;
        _progress = Math.min(100, _progress + (delta / dur) * 100);

        const fill = document.getElementById(`sv-prog-${_si}`);
        if (fill) fill.style.width = _progress + '%';

        if (_progress >= 100) {
            _nextStory();
            return;
        }
        _raf = requestAnimationFrame(animate);
    };
    _raf = requestAnimationFrame(animate);
}

function _stopProgress() {
    if (_raf) { cancelAnimationFrame(_raf); _raf = null; }
}

function _nextStory() {
    _stopProgress();
    const group = _groups[_gi];
    if (!group) { closeStoryViewer(); return; }
    if (_si < group.stories.length - 1) {
        _si++;
        _progress = 0;
        _renderCurrent();
        _startProgress();
        _markViewed();
    } else if (_gi < _groups.length - 1) {
        _gi++;
        _si = 0;
        _progress = 0;
        _renderCurrent();
        _startProgress();
        _markViewed();
    } else {
        closeStoryViewer();
    }
}

function _prevStory() {
    _stopProgress();
    if (_si > 0) {
        _si--;
    } else if (_gi > 0) {
        _gi--;
        _si = _groups[_gi].stories.length - 1;
    }
    _progress = 0;
    _renderCurrent();
    _startProgress();
}

function _markViewed() {
    const group = _groups[_gi];
    if (!group || group.is_self) return;
    const story = group.stories[_si];
    if (!story) return;
    api('POST', `/api/stories/${story.id}/view`).catch(() => {});

    // Mark group as seen and re-sort: viewed stories go to the end
    group.has_unseen = false;
    _sortGroups();
    renderStoriesStrip();
}

function _sortGroups() {
    // Self always first, then unseen, then seen
    _groups.sort(function(a, b) {
        if (a.is_self) return -1;
        if (b.is_self) return 1;
        var aUnseen = a.has_unseen !== false ? 1 : 0;
        var bUnseen = b.has_unseen !== false ? 1 : 0;
        return bUnseen - aUnseen;
    });
}

// Hold to pause
window._svTapStart = function(e, side) {
    e.preventDefault();
    _holdTimer = setTimeout(() => {
        _paused = true;
        _holdTimer = null;
    }, 150);
};

window._svTapEnd = function(e, side) {
    e.preventDefault();
    if (_holdTimer) {
        clearTimeout(_holdTimer);
        _holdTimer = null;
        // Short tap → navigate
        if (side === 'right') _nextStory();
        else _prevStory();
    } else {
        // Was holding → resume
        _paused = false;
    }
};

window.closeStoryViewer = closeStoryViewer;
window.openStories = openStories;

window._deleteCurrentStory = async function() {
    const group = _groups[_gi];
    if (!group || !group.is_self) return;
    const story = group.stories[_si];
    if (!story) return;
    try {
        await api('DELETE', `/api/stories/${story.id}`);
        group.stories.splice(_si, 1);
        if (!group.stories.length) {
            _groups.splice(_gi, 1);
            if (!_groups.length) { closeStoryViewer(); renderStoriesStrip(); return; }
            _gi = Math.min(_gi, _groups.length - 1);
            _si = 0;
        } else {
            _si = Math.min(_si, group.stories.length - 1);
        }
        _renderCurrent();
        _startProgress();
        renderStoriesStrip();
    } catch (e) {
        alert(e.message);
    }
};

// ── Story Reactions & Replies ────────────────────────────────────────────────

window._svReact = async function(emoji) {
    const group = _groups[_gi];
    if (!group || group.is_self) return;
    const story = group.stories[_si];
    if (!story) return;
    try {
        const fd = new FormData();
        fd.append('emoji', emoji);
        await fetch('/api/stories/' + story.id + '/react', {
            method: 'POST', credentials: 'include', body: fd,
            headers: { 'X-CSRF-Token': window.AppState?.csrfToken || '' },
        });
        // Visual feedback
        const btn = event?.target?.closest('.sv-react-btn');
        if (btn) {
            btn.style.transform = 'scale(1.5)';
            setTimeout(() => { btn.style.transform = ''; }, 300);
        }
        window.showToast?.((window.t?.('notifications.reactionSent')||'Reaction sent'), 'success');
    } catch {}
};

window._svSendReply = async function() {
    const group = _groups[_gi];
    if (!group || group.is_self) return;
    const story = group.stories[_si];
    if (!story) return;
    const input = document.getElementById('sv-reply-input');
    if (!input || !input.value.trim()) return;
    try {
        const fd = new FormData();
        fd.append('text', input.value.trim());
        await fetch('/api/stories/' + story.id + '/reply', {
            method: 'POST', credentials: 'include', body: fd,
            headers: { 'X-CSRF-Token': window.AppState?.csrfToken || '' },
        });
        input.value = '';
        window.showToast?.((window.t?.('notifications.replySent')||'Reply sent'), 'success');
    } catch {}
};

window._svPause = function() { _paused = true; _stopProgress(); };
window._svResume = function() { _paused = false; _startProgress(); };

function _timeAgo(iso) {
    if (!iso) return '';
    const d = new Date(/Z$|[+-]\d{2}/.test(iso) ? iso : iso + 'Z');
    const diff = Math.round((Date.now() - d.getTime()) / 60000);
    const _t = window.t || ((k) => k);
    if (diff < 1) return _t('time.justNow');
    if (diff < 60) return diff + ' ' + _t('time.minShort');
    if (diff < 1440) return Math.round(diff / 60) + ' ' + _t('time.hShort');
    return Math.round(diff / 1440) + ' ' + _t('time.dShort');
}

// ── Story Creator ─────────────────────────────────────────────────────────────
export function showStoryCreator() {
    _scFile = null;
    _scMusicFile = null;
    _scType = null;
    const page = document.getElementById('story-create-modal');
    if (!page) return;
    page.style.display = 'flex';
    document.getElementById('sc-step-type').style.display = 'flex';
    document.getElementById('sc-step-editor').style.display = 'none';
}

export function closeStoryCreator() {
    const page = document.getElementById('story-create-modal');
    if (page) page.style.display = 'none';
    _stopCamera();
    _scFile = null;
    _scMusicFile = null;
}

window.showStoryCreator = showStoryCreator;
window.closeStoryCreator = closeStoryCreator;
window.expandStories = expandStories;
window.collapseStories = collapseStories;
window.loadStories = loadStories;

window._scBack = function() {
    _stopCamera();
    document.getElementById('sc-step-type').style.display = 'flex';
    document.getElementById('sc-step-editor').style.display = 'none';
};

window._scSelectType = async function(type) {
    _scType = type;
    document.getElementById('sc-step-type').style.display = 'none';
    document.getElementById('sc-step-editor').style.display = 'flex';

    // Reset all editor sections
    ['sc-camera-wrap','sc-preview-wrap','sc-text-editor','sc-duration-group','sc-overlay-group'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    const _t = window.t || ((k) => k);
    document.getElementById('sc-editor-title').textContent = {
        photo: _t('stories.editorPhoto'),
        video: _t('stories.editorVideo'),
        text:  _t('stories.editorText'),
        music: _t('stories.editorMusic'),
        'camera-photo': _t('stories.editorCamera'),
        'camera-video': _t('stories.editorCamera'),
    }[type] || _t('stories.editor');

    if (type === 'photo') {
        document.getElementById('sc-photo-file').click();
        document.getElementById('sc-overlay-group').style.display = '';
        document.getElementById('sc-duration-group').style.display = '';
    } else if (type === 'video') {
        document.getElementById('sc-video-file').click();
    } else if (type === 'text') {
        document.getElementById('sc-text-editor').style.display = '';
        document.getElementById('sc-duration-group').style.display = '';
        _scUpdateTextPreview();
    } else if (type === 'music') {
        document.getElementById('sc-text-editor').style.display = '';
        document.getElementById('sc-duration-group').style.display = '';
        _scUpdateTextPreview();
    } else if (type === 'camera-photo' || type === 'camera-video') {
        document.getElementById('sc-camera-wrap').style.display = '';
        document.getElementById('sc-overlay-group').style.display = '';
        if (type === 'camera-photo') document.getElementById('sc-duration-group').style.display = '';
        await _startCamera();
        // Show/hide record vs capture buttons
        document.getElementById('sc-capture-btn').style.display = type === 'camera-photo' ? '' : 'none';
        document.getElementById('sc-record-btn').style.display  = type === 'camera-video' ? '' : 'none';
    }
};

// Camera
async function _startCamera() {
    try {
        _camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: true });
        const v = document.getElementById('sc-camera-stream');
        if (v) { v.srcObject = _camStream; }
    } catch {
        alert(window.t ? window.t('stories.noCamera') : 'No camera access');
    }
}

function _stopCamera() {
    if (_camStream) { _camStream.getTracks().forEach(t => t.stop()); _camStream = null; }
    if (_camRecorder) { try { _camRecorder.stop(); } catch {} _camRecorder = null; }
    _isRecording = false;
}

window._scCapture = function() {
    const video = document.getElementById('sc-camera-stream');
    const canvas = document.getElementById('sc-canvas');
    if (!video || !canvas) return;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
        _scFile = new File([blob], 'story.jpg', { type: 'image/jpeg' });
        _scType = 'photo';
        _stopCamera();
        document.getElementById('sc-camera-wrap').style.display = 'none';
        document.getElementById('sc-preview-wrap').style.display = '';
        const img = document.getElementById('sc-preview-img');
        img.src = URL.createObjectURL(blob);
        img.style.display = 'block';
    }, 'image/jpeg', 0.9);
};

window._scToggleCamRecord = function() {
    if (!_isRecording) {
        _camChunks = [];
        const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9') ? 'video/webm;codecs=vp9' : 'video/webm';
        _camRecorder = new MediaRecorder(_camStream, { mimeType: mime });
        _camRecorder.ondataavailable = e => { if (e.data.size > 0) _camChunks.push(e.data); };
        _camRecorder.onstop = () => {
            const blob = new Blob(_camChunks, { type: 'video/webm' });
            _scFile = new File([blob], 'story.webm', { type: 'video/webm' });
            _scType = 'video';
            _stopCamera();
            document.getElementById('sc-camera-wrap').style.display = 'none';
            document.getElementById('sc-preview-wrap').style.display = '';
            const vid = document.getElementById('sc-preview-video');
            vid.src = URL.createObjectURL(blob);
            vid.style.display = 'block';
        };
        _camRecorder.start();
        _isRecording = true;
        document.getElementById('sc-record-btn').textContent = '⏹ ' + (window.t ? window.t('stories.stopRecording') : 'Stop');
        document.getElementById('sc-record-btn').style.background = 'var(--red)';
    } else {
        _camRecorder.stop();
        _isRecording = false;
        document.getElementById('sc-record-btn').textContent = '⏺ ' + (window.t ? window.t('stories.startRecording') : 'Record');
        document.getElementById('sc-record-btn').style.background = '';
    }
};

window._scMediaFileChange = function(input, type) {
    const file = input.files?.[0];
    if (!file) return;
    _scFile = file;
    _scType = type;
    document.getElementById('sc-preview-wrap').style.display = '';
    const url = URL.createObjectURL(file);
    if (type === 'photo') {
        const img = document.getElementById('sc-preview-img');
        img.src = url; img.style.display = 'block';
        document.getElementById('sc-preview-video').style.display = 'none';
    } else {
        const vid = document.getElementById('sc-preview-video');
        vid.src = url; vid.style.display = 'block';
        document.getElementById('sc-preview-img').style.display = 'none';
    }
};

window._scMusicFileChange = function(input) {
    const file = input.files?.[0];
    if (!file) return;
    _scMusicFile = file;
    const prev = document.getElementById('sc-music-preview');
    prev.textContent = '♫ ' + file.name;
    prev.style.display = '';
};

window._scUpdateTextPreview = function() {
    const text = document.getElementById('sc-text-input')?.value || '';
    const p = document.getElementById('sc-text-preview-content');
    if (p) { p.textContent = text; p.style.color = _scTextColor; }
    const preview = document.getElementById('sc-text-preview');
    if (preview) preview.style.background = _scBg;
};

window._scSetTextColor = function(color, btn) {
    _scTextColor = color;
    document.querySelectorAll('#sc-text-colors .sc-color-dot').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _scUpdateTextPreview();
};

window._scSetBg = function(bg, btn) {
    _scBg = bg;
    document.querySelectorAll('#sc-bg-colors .sc-bg-dot').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    _scUpdateTextPreview();
};

window._scPublish = async function() {
    const btn = document.getElementById('sc-publish-btn');
    btn.disabled = true;
    btn.textContent = window.t ? window.t('stories.publishing') : 'Publishing...';
    try {
        const fd = new FormData();
        const mediaType = ['camera-photo','photo'].includes(_scType) ? 'photo'
            : ['camera-video','video'].includes(_scType) ? 'video' : 'text';
        fd.append('media_type', mediaType);

        // ── E2E Encryption ─────────────────────────────────────────────
        // 1. Generate random story key
        const storyKey = generateStoryKey();

        // 2. Encrypt media blob
        if (_scFile) {
            const rawBuf = await _scFile.arrayBuffer();
            const encBuf = await storyEncryptBlob(rawBuf, storyKey);
            fd.append('file', new Blob([encBuf]), 'story.enc');
        }

        // 3. Encrypt music blob
        if (_scMusicFile) {
            const rawBuf = await _scMusicFile.arrayBuffer();
            const encBuf = await storyEncryptBlob(rawBuf, storyKey);
            fd.append('music_file', new Blob([encBuf]), 'music.enc');
        }

        // 4. Encrypt text
        const overlayText = document.getElementById('sc-overlay-text')?.value.trim();
        const mainText = document.getElementById('sc-text-input')?.value.trim();
        const plainText = overlayText || mainText || '';
        if (plainText) {
            const textCt = await storyEncrypt(plainText, storyKey);
            fd.append('text_ct', textCt);
        }

        // 5. Encrypt metadata (text_color, bg_color, music_title)
        const musicTitle = document.getElementById('sc-music-title')?.value.trim() || '';
        const metaJson = JSON.stringify({
            text_color: _scTextColor,
            bg_color: _scBg,
            music_title: musicTitle,
        });
        const metaCt = await storyEncrypt(metaJson, storyKey);
        fd.append('meta_ct', metaCt);

        const dur = document.getElementById('sc-duration-input')?.value || '5';
        fd.append('duration', dur);

        // 6. Wrap story_key for each contact via ECIES
        const contacts = await _getContactPubKeys();
        const envelopes = await wrapStoryKeyForContacts(storyKey, contacts);

        // Also wrap for self (so we can view our own stories)
        const S = window.AppState;
        const myPub = localStorage.getItem('vortex_x25519_pub');
        if (myPub) {
            try {
                const selfEnv = await eciesEncrypt(storyKey, myPub);
                envelopes.push({ user_id: S.user?.id, ...selfEnv });
            } catch {}
        }

        fd.append('key_envelopes', JSON.stringify(envelopes));

        // 7. Upload
        const csrf = S?.csrfToken || '';
        const resp = await fetch('/api/stories', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrf },
            body: fd,
            credentials: 'include',
        });
        if (!resp.ok) throw new Error(await resp.text());
        const story = await resp.json();

        // Add to own group
        let selfGroup = _groups.find(g => g.is_self);
        if (!selfGroup) {
            selfGroup = {
                user_id: S.user?.id,
                username: S.user?.username,
                display_name: S.user?.display_name || S.user?.username,
                avatar_emoji: S.user?.avatar_emoji,
                avatar_url: S.user?.avatar_url,
                is_self: true,
                stories: [],
                has_unseen: false,
            };
            _groups.unshift(selfGroup);
        }
        selfGroup.stories.push(story);

        closeStoryCreator();
        renderStoriesStrip();
    } catch (e) {
        console.error('[STORY] Publish error:', e);
        const errMsg = window.t ? window.t('stories.publishError').replace('{error}', e.message) : ('Error: ' + e.message);
        alert(errMsg);
    } finally {
        btn.disabled = false;
        btn.textContent = window.t ? window.t('stories.publish') : 'Publish';
    }
};

/** Fetch contact public keys for ECIES wrapping. */
async function _getContactPubKeys() {
    try {
        const data = await api('GET', '/api/contacts');
        const contacts = data.contacts || data || [];
        const result = [];
        for (const c of contacts) {
            const uid = c.contact_id || c.id;
            const pub = c.x25519_public_key || c.x25519_pub || c.pub_key;
            if (uid && pub) result.push({ user_id: uid, pub_key: pub });
        }
        return result;
    } catch {
        return [];
    }
}
