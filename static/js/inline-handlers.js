// Safe i18n wrapper — inline-handlers.js loads before main.js (which sets window.t)
var _i18nRef = null;
function t(key, params) {
    if (!_i18nRef && window._i18n_t) _i18nRef = window._i18n_t;
    if (_i18nRef) return _i18nRef(key, params);
    var s = key.split('.').pop();
    return params ? s.replace(/\{(\w+)\}/g, function(_, k) { return params[k] != null ? params[k] : k; }) : s;
}

// ── Vortex Custom Video Player ──
window._openVideoViewer = async function(downloadUrl, fileName) {
    document.getElementById('video-viewer-overlay')?.remove();

    // Load timecodes from sessionStorage if available
    var timecodes = [];
    try {
        var raw = sessionStorage.getItem('vortex_vtc_' + (fileName || ''));
        if (raw) timecodes = JSON.parse(raw);
    } catch(e) {}

    var _hideTimer = null;
    var _speedIdx = 3; // index in speeds array
    var speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3];

    // ── Overlay ──
    var overlay = document.createElement('div');
    overlay.id = 'video-viewer-overlay';
    overlay.className = 'vp-overlay';

    // ── Video container ──
    var container = document.createElement('div');
    container.className = 'vp-container';

    // ── Video element ──
    var video = document.createElement('video');
    video.className = 'vp-video';
    video.playsInline = true;
    video.preload = 'auto';

    // ── Big play button (center) ──
    var bigPlay = document.createElement('div');
    bigPlay.className = 'vp-big-play';
    bigPlay.innerHTML = '<svg width="64" height="64" viewBox="0 0 24 24" fill="white" opacity=".9"><path d="M8 5v14l11-7z"/></svg>';

    // ── Header ──
    var header = document.createElement('div');
    header.className = 'vp-header';
    var nameEl = document.createElement('div');
    nameEl.className = 'vp-name';
    nameEl.textContent = fileName || 'Video';
    var closeBtn = document.createElement('button');
    closeBtn.className = 'vp-close';
    closeBtn.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    header.append(nameEl, closeBtn);

    // ── Controls bar ──
    var controls = document.createElement('div');
    controls.className = 'vp-controls';

    // Progress bar
    var progressWrap = document.createElement('div');
    progressWrap.className = 'vp-progress-wrap';
    var progressBuf = document.createElement('div');
    progressBuf.className = 'vp-progress-buf';
    var progressFill = document.createElement('div');
    progressFill.className = 'vp-progress-fill';
    var progressThumb = document.createElement('div');
    progressThumb.className = 'vp-progress-thumb';
    var progressHover = document.createElement('div');
    progressHover.className = 'vp-progress-hover';
    progressWrap.append(progressBuf, progressFill, progressThumb, progressHover);

    // Timecode markers on progress bar
    // (will be positioned after duration is known)

    // Bottom row: play, time, spacer, volume, speed, pip, fullscreen
    var bottomRow = document.createElement('div');
    bottomRow.className = 'vp-bottom';

    var playBtn = document.createElement('button');
    playBtn.className = 'vp-btn';
    var ICON_PLAY = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
    var ICON_PAUSE = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>';
    playBtn.innerHTML = ICON_PLAY;

    var timeEl = document.createElement('div');
    timeEl.className = 'vp-time';
    timeEl.textContent = '0:00 / 0:00';

    var spacer = document.createElement('div');
    spacer.style.flex = '1';

    // Volume
    var volWrap = document.createElement('div');
    volWrap.className = 'vp-vol-wrap';
    var volBtn = document.createElement('button');
    volBtn.className = 'vp-btn';
    volBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg>';
    var volSlider = document.createElement('input');
    volSlider.type = 'range'; volSlider.min = '0'; volSlider.max = '1'; volSlider.step = '0.05'; volSlider.value = '1';
    volSlider.className = 'vp-vol-slider';
    volWrap.append(volBtn, volSlider);

    // Speed
    var speedBtn = document.createElement('button');
    speedBtn.className = 'vp-btn vp-speed-btn';
    speedBtn.textContent = '1x';

    // PiP
    var pipBtn = document.createElement('button');
    pipBtn.className = 'vp-btn';
    pipBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2"/><rect x="12" y="10" width="8" height="6" rx="1" fill="currentColor" opacity=".3"/></svg>';

    // Fullscreen
    var fsBtn = document.createElement('button');
    fsBtn.className = 'vp-btn';
    fsBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>';

    bottomRow.append(playBtn, timeEl, spacer, volWrap, speedBtn, pipBtn, fsBtn);
    controls.append(progressWrap, bottomRow);

    // ── Chapters panel ──
    var chaptersPanel = null;
    if (timecodes.length) {
        chaptersPanel = document.createElement('div');
        chaptersPanel.className = 'vp-chapters';
        var chapTitle = document.createElement('div');
        chapTitle.className = 'vp-chapters-title';
        chapTitle.textContent = 'Chapters';
        chaptersPanel.appendChild(chapTitle);
        timecodes.forEach(function(tc) {
            var row = document.createElement('div');
            row.className = 'vp-chapter';
            row.dataset.time = tc.time;
            var badge = document.createElement('span');
            badge.className = 'vp-chapter-time';
            badge.textContent = _fmtTime(tc.time);
            var label = document.createElement('span');
            label.className = 'vp-chapter-label';
            label.textContent = tc.label;
            row.append(badge, label);
            row.addEventListener('click', function() { video.currentTime = tc.time; if (video.paused) video.play(); });
            chaptersPanel.appendChild(row);
        });
    }

    container.append(video, bigPlay, header, controls);
    overlay.appendChild(container);
    if (chaptersPanel) overlay.appendChild(chaptersPanel);
    document.body.appendChild(overlay);

    // ── Format time helper ──
    function _fmtTime(s) {
        if (!s || isNaN(s)) return '0:00';
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = Math.floor(s % 60);
        if (h > 0) return h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
        return m + ':' + String(sec).padStart(2, '0');
    }

    // ── Show/hide controls ──
    function showControls() {
        container.classList.add('vp-show-ui');
        clearTimeout(_hideTimer);
        _hideTimer = setTimeout(function() {
            if (!video.paused) container.classList.remove('vp-show-ui');
        }, 3000);
    }
    container.addEventListener('mousemove', showControls);
    container.addEventListener('touchstart', showControls, { passive: true });

    // ── Load video ──
    if (downloadUrl.startsWith('blob:')) {
        // Already decrypted blob URL — use directly
        video.src = downloadUrl;
    } else {
        try {
            var resp = await fetch(downloadUrl, { credentials: 'include' });
            var data = await resp.arrayBuffer();
            try {
                var mod = await import('./crypto.js');
                var rk = mod.getRoomKey(window.AppState?.currentRoom?.id);
                if (rk && data.byteLength > 12) data = await mod.decryptFile(data, rk);
            } catch(e) {}
            video.src = URL.createObjectURL(new Blob([data]));
        } catch(e) {
            video.src = downloadUrl;
        }
    }
    video.play().catch(function() {});

    // ── Add timecode markers to progress bar after duration known ──
    video.addEventListener('loadedmetadata', function() {
        if (timecodes.length && video.duration) {
            timecodes.forEach(function(tc) {
                var marker = document.createElement('div');
                marker.className = 'vp-tc-marker';
                marker.style.left = (tc.time / video.duration * 100) + '%';
                marker.title = tc.label;
                progressWrap.appendChild(marker);
            });
        }
    });

    // ── Event handlers ──
    video.addEventListener('play', function() {
        playBtn.innerHTML = ICON_PAUSE;
        bigPlay.classList.add('hidden');
        showControls();
    });
    video.addEventListener('pause', function() {
        playBtn.innerHTML = ICON_PLAY;
        bigPlay.classList.remove('hidden');
        container.classList.add('vp-show-ui');
        clearTimeout(_hideTimer);
    });
    video.addEventListener('ended', function() {
        playBtn.innerHTML = ICON_PLAY;
        bigPlay.classList.remove('hidden');
        container.classList.add('vp-show-ui');
    });
    video.addEventListener('timeupdate', function() {
        if (!video.duration) return;
        var pct = video.currentTime / video.duration * 100;
        progressFill.style.width = pct + '%';
        progressThumb.style.left = pct + '%';
        timeEl.textContent = _fmtTime(video.currentTime) + ' / ' + _fmtTime(video.duration);
        // Highlight active chapter
        if (chaptersPanel) {
            var active = null;
            timecodes.forEach(function(tc) { if (video.currentTime >= tc.time) active = tc; });
            chaptersPanel.querySelectorAll('.vp-chapter').forEach(function(el) {
                el.classList.toggle('active', active && parseFloat(el.dataset.time) === active.time);
            });
        }
    });
    video.addEventListener('progress', function() {
        if (video.buffered.length && video.duration) {
            progressBuf.style.width = (video.buffered.end(video.buffered.length - 1) / video.duration * 100) + '%';
        }
    });

    // Play/Pause
    function togglePlay() { video.paused ? video.play() : video.pause(); }
    playBtn.addEventListener('click', togglePlay);
    bigPlay.addEventListener('click', togglePlay);
    video.addEventListener('click', togglePlay);

    // Double-click fullscreen
    video.addEventListener('dblclick', function(e) {
        e.preventDefault();
        if (document.fullscreenElement) document.exitFullscreen();
        else container.requestFullscreen?.();
    });

    // Progress bar seek
    function seekFromEvent(e) {
        var rect = progressWrap.getBoundingClientRect();
        var pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        video.currentTime = pct * video.duration;
    }
    progressWrap.addEventListener('click', seekFromEvent);
    var _dragging = false;
    progressWrap.addEventListener('mousedown', function(e) {
        _dragging = true; seekFromEvent(e);
        document.addEventListener('mousemove', onDragSeek);
        document.addEventListener('mouseup', onDragEnd);
    });
    function onDragSeek(e) { if (_dragging) seekFromEvent(e); }
    function onDragEnd() { _dragging = false; document.removeEventListener('mousemove', onDragSeek); document.removeEventListener('mouseup', onDragEnd); }
    // Hover time tooltip
    progressWrap.addEventListener('mousemove', function(e) {
        var rect = progressWrap.getBoundingClientRect();
        var pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        progressHover.style.left = (pct * 100) + '%';
        progressHover.textContent = _fmtTime(pct * (video.duration || 0));
        progressHover.classList.add('show');
    });
    progressWrap.addEventListener('mouseleave', function() { progressHover.classList.remove('show'); });

    // Volume
    volSlider.addEventListener('input', function() {
        video.volume = parseFloat(volSlider.value);
        video.muted = false;
        updateVolIcon();
    });
    volBtn.addEventListener('click', function() {
        video.muted = !video.muted;
        if (!video.muted && video.volume === 0) { video.volume = 0.5; volSlider.value = '0.5'; }
        updateVolIcon();
    });
    function updateVolIcon() {
        var v = video.muted ? 0 : video.volume;
        volSlider.value = String(video.muted ? 0 : video.volume);
        if (v === 0) volBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>';
        else if (v < 0.5) volBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg>';
        else volBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg>';
    }

    // Speed
    speedBtn.addEventListener('click', function() {
        _speedIdx = (_speedIdx + 1) % speeds.length;
        video.playbackRate = speeds[_speedIdx];
        speedBtn.textContent = speeds[_speedIdx] + 'x';
    });

    // PiP
    pipBtn.addEventListener('click', function() {
        if (document.pictureInPictureElement) document.exitPictureInPicture();
        else video.requestPictureInPicture?.();
    });
    if (!document.pictureInPictureEnabled) pipBtn.style.display = 'none';

    // Fullscreen
    fsBtn.addEventListener('click', function() {
        if (document.fullscreenElement) document.exitFullscreen();
        else container.requestFullscreen?.();
    });

    // Close
    function closePlayer() {
        video.pause(); video.src = '';
        overlay.remove();
        document.removeEventListener('keydown', keyHandler);
    }
    closeBtn.addEventListener('click', closePlayer);
    overlay.addEventListener('click', function(e) { if (e.target === overlay) closePlayer(); });

    // Keyboard
    function keyHandler(e) {
        if (!overlay.isConnected) { document.removeEventListener('keydown', keyHandler); return; }
        var k = e.key;
        if (k === 'Escape') { closePlayer(); return; }
        if (k === ' ' || k === 'k') { e.preventDefault(); togglePlay(); }
        else if (k === 'ArrowLeft') { e.preventDefault(); video.currentTime = Math.max(0, video.currentTime - (e.shiftKey ? 10 : 5)); }
        else if (k === 'ArrowRight') { e.preventDefault(); video.currentTime = Math.min(video.duration, video.currentTime + (e.shiftKey ? 10 : 5)); }
        else if (k === 'ArrowUp') { e.preventDefault(); video.volume = Math.min(1, video.volume + 0.1); volSlider.value = String(video.volume); updateVolIcon(); }
        else if (k === 'ArrowDown') { e.preventDefault(); video.volume = Math.max(0, video.volume - 0.1); volSlider.value = String(video.volume); updateVolIcon(); }
        else if (k === 'm') { video.muted = !video.muted; updateVolIcon(); }
        else if (k === 'f') { if (document.fullscreenElement) document.exitFullscreen(); else container.requestFullscreen?.(); }
        else if (k === 'j') { video.currentTime = Math.max(0, video.currentTime - 10); }
        else if (k === 'l') { video.currentTime = Math.min(video.duration, video.currentTime + 10); }
    }
    document.addEventListener('keydown', keyHandler);

    showControls();
};

// ── Document Viewer ──
window._openDocViewer = async function(downloadUrl, fileName, ext) {
    var overlay = document.getElementById('doc-viewer-overlay');
    var content = document.getElementById('doc-viewer-content');
    var title = document.getElementById('doc-viewer-title');
    var icon = document.getElementById('doc-viewer-icon');
    var dl = document.getElementById('doc-viewer-dl');
    if (!overlay || !content) return;

    if (title) title.textContent = fileName || 'Document';
    if (dl) dl.href = downloadUrl;

    var colors = { pdf:'#ef4444', doc:'#2563eb', docx:'#2563eb', txt:'#6b7280', py:'#3572a5', js:'#eab308', css:'#2563eb', json:'#eab308', md:'#8b5cf6' };
    if (icon) {
        icon.style.background = colors[ext] || '#6b7280';
        icon.textContent = (ext || '?').toUpperCase().slice(0, 4);
    }

    content.textContent = '';

    var textExts = ['txt','md','log','csv','json','xml','yaml','yml','py','js','ts','css','html','htm','c','cpp','cs','go','rs','rb','java','php','sh','sql','swift','kt','dart','rtf'];
    var isPdf = ext === 'pdf';
    var isText = textExts.indexOf(ext) >= 0;

    if (isPdf) {
        var iframe = document.createElement('iframe');
        iframe.src = downloadUrl;
        iframe.style.cssText = 'width:100%;height:100%;border:none;background:#fff;';
        content.appendChild(iframe);
    } else if (isText) {
        try {
            var resp = await fetch(downloadUrl, { credentials: 'include' });
            var data = await resp.arrayBuffer();
            // Try E2E decrypt
            try {
                var mod = await import('./crypto.js');
                var rk = mod.getRoomKey(window.AppState?.currentRoom?.id);
                if (rk && data.byteLength > 12) data = await mod.decryptFile(data, rk);
            } catch(e) {}
            var text = new TextDecoder().decode(data);
            var pre = document.createElement('pre');
            pre.style.cssText = 'padding:20px;margin:0;font-family:var(--mono,monospace);font-size:13px;color:var(--text);line-height:1.6;white-space:pre-wrap;word-break:break-word;background:var(--bg);min-height:100%;';
            // Add line numbers
            var lines = text.split('\n');
            for (var i = 0; i < lines.length; i++) {
                var lineNum = document.createElement('span');
                lineNum.style.cssText = 'color:var(--text3);user-select:none;display:inline-block;width:40px;text-align:right;margin-right:16px;font-size:11px;';
                lineNum.textContent = String(i + 1);
                pre.appendChild(lineNum);
                pre.appendChild(document.createTextNode(lines[i] + '\n'));
            }
            content.appendChild(pre);
        } catch(e) {
            content.textContent = t('errors.loadError', {message: e.message});
        }
    } else {
        content.textContent = t('files.previewUnavailable');
        content.style.cssText = 'display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:14px;';
    }

    overlay.style.display = 'flex';
};

window._closeDocViewer = function() {
    var overlay = document.getElementById('doc-viewer-overlay');
    if (overlay) {
        overlay.style.display = 'none';
        var content = document.getElementById('doc-viewer-content');
        if (content) content.textContent = '';
    }
};

// ── Space create/join tab switching ──
window._switchCsTab = function(tab) {
    var createPanel = document.getElementById('cs-panel-create');
    var joinPanel = document.getElementById('cs-panel-join');
    var tabs = document.querySelectorAll('#create-space-modal .cs-tab');
    tabs.forEach(function(t, i) {
        t.classList.toggle('active', (tab === 'create' && i === 0) || (tab === 'join' && i === 1));
    });
    if (createPanel) createPanel.classList.toggle('active', tab === 'create');
    if (joinPanel) joinPanel.classList.toggle('active', tab === 'join');
};

// ── Avatar tab switching (registration form) ──
window.switchAvatarTab = function(tab) {
    var emojiTab = document.getElementById('avatar-emoji-tab');
    var photoTab = document.getElementById('avatar-photo-tab');
    var emojiPanel = document.getElementById('avatar-emoji-panel');
    var photoPanel = document.getElementById('avatar-photo-panel');
    if (tab === 'emoji') {
        if (emojiTab) emojiTab.classList.add('active');
        if (photoTab) photoTab.classList.remove('active');
        if (emojiPanel) emojiPanel.style.display = '';
        if (photoPanel) photoPanel.style.display = 'none';
    } else {
        if (emojiTab) emojiTab.classList.remove('active');
        if (photoTab) photoTab.classList.add('active');
        if (emojiPanel) emojiPanel.style.display = 'none';
        if (photoPanel) photoPanel.style.display = '';
    }
};

window.previewAvatar = function(input) {
    if (!input.files || !input.files[0]) return;
    var reader = new FileReader();
    reader.onload = function(e) {
        var preview = document.getElementById('avatar-preview');
        if (preview) preview.innerHTML = '<img src="' + e.target.result + '" style="width:100%;height:100%;object-fit:cover;">';
    };
    reader.readAsDataURL(input.files[0]);
};

// ── Settings tab switching (legacy stub, sections now open full-screen) ──
window.switchSettingsTab = function(tab) {};

// ── Settings emoji picker ──
window._settingsSelectedEmoji = null;
window.selectSettingsEmoji = function(btn) {
    document.querySelectorAll('#settings-emoji-picker .emoji-btn').forEach(function(b) { b.classList.remove('emoji-selected'); });
    btn.classList.add('emoji-selected');
    window._settingsSelectedEmoji = btn.dataset.emoji;
};

// ── Save profile from settings ──
window.saveProfileSettings = async function() {
    var S = window.AppState;
    var body = {
        display_name: document.getElementById('set-display-name')?.value?.trim() || undefined,
        email: document.getElementById('set-email')?.value?.trim() || undefined,
        bio: document.getElementById('set-bio')?.value?.trim() ?? undefined,
    };
    if (window._settingsSelectedEmoji) {
        body.avatar_emoji = window._settingsSelectedEmoji;
    }
    // Birthday — only send if user actually changed it via the picker
    var bdBtn = document.getElementById('set-birthday-btn');
    if (bdBtn && bdBtn.dataset.dirty === '1') {
        body.birth_date = bdBtn.dataset.value;
    }
    // Profile background
    if (window._settingsProfileBg !== undefined) {
        body.profile_bg = window._settingsProfileBg;
    }
    // Profile icon
    if (window._settingsProfileIcon !== undefined) {
        body.profile_icon = window._settingsProfileIcon;
    }
    try {
        var resp = await window.api('PUT', '/api/authentication/profile', body);
        if (resp.display_name !== undefined) {
            S.user.display_name = resp.display_name;
            var sbName = document.getElementById('sb-name');
            if (sbName) sbName.textContent = resp.display_name;
        }
        if (resp.avatar_emoji !== undefined) {
            S.user.avatar_emoji = resp.avatar_emoji;
            if (!S.user.avatar_url) {
                var sbAv = document.getElementById('sb-avatar');
                if (sbAv) sbAv.textContent = resp.avatar_emoji;
            }
        }
        if (resp.email      !== undefined) S.user.email      = resp.email;
        if (resp.bio        !== undefined) S.user.bio        = resp.bio;
        if (resp.birth_date !== undefined) S.user.birth_date = resp.birth_date;
        if (resp.profile_bg  !== undefined) S.user.profile_bg  = resp.profile_bg;
        if (resp.profile_icon !== undefined) S.user.profile_icon = resp.profile_icon;
        alert(window.t?.('notifications.saved')||'Saved');
    } catch(e) { alert(e.message); }
};

// ── Profile background picker ──
window._settingsProfileBg = undefined;
window._selectProfileBg = function(btn) {
    document.querySelectorAll('.pbg-swatch').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    window._settingsProfileBg = btn.dataset.bg;
    var preview = document.getElementById('set-profile-bg-preview');
    if (preview) preview.style.background = btn.dataset.bg;
    // Sync icon preview background
    var piHero = document.getElementById('pi-preview-hero');
    if (piHero) piHero.style.background = btn.dataset.bg;
};

// ── Profile icon registry (shared with user-profile.js) ──
window._PROFILE_ICONS = {
  bolt:     '<path d="M7 2v11h3v9l7-12h-4l4-8z"/>',
  diamond:  '<path d="M12 1l10 8-10 13L2 9z"/>',
  flame:    '<path d="M12 23c-3.87 0-7-3.13-7-7 0-4 2.5-7.5 7-14 4.5 6.5 7 10 7 14 0 3.87-3.13 7-7 7z"/>',
  moon:     '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  star:     '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/>',
  crown:    '<path d="M2 20v-2h20v2H2zm2-4 3-11 5 3 5-3 3 11H4z"/>',
  shield:   '<path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5z"/>',
  eye:      '<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zm0 12.5c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>',
  drop:     '<path d="M12 2C8.13 6 5 10 5 14c0 3.87 3.13 7 7 7s7-3.13 7-7c0-4-3.13-8-7-12z"/>',
  hexagon:  '<path d="M17.27 4H6.73L2 12l4.73 8h10.54L22 12z"/>',
  target:   '<path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm0-12a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"/>',
  compass:  '<path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>',
  crystal:  '<path d="M16.5 3h-9L3 9.5 12 21l9-11.5L16.5 3zM9.14 4.5h5.72L17.7 9H6.3l2.84-4.5zM12 18.5 5.63 10.5h12.74L12 18.5z"/>',
  infinity: '<path d="M18.6 6.62c-1.44 0-2.8.56-3.77 1.53L12 10.66l-2.83-2.51A5.37 5.37 0 0 0 5.4 6.62C2.42 6.62 0 9.04 0 12s2.42 5.38 5.4 5.38c1.44 0 2.8-.56 3.77-1.53L12 13.34l2.83 2.51a5.37 5.37 0 0 0 3.77 1.53C21.58 17.38 24 14.96 24 12s-2.42-5.38-5.4-5.38zm-13.2 8.76c-1.87 0-3.39-1.52-3.39-3.38s1.52-3.38 3.39-3.38c.9 0 1.76.35 2.44 1.03L8.87 12l-1.43 1.27c-.68.68-1.54 1.11-2.44 1.11zm13.2 0c-.9 0-1.76-.43-2.44-1.11L15.13 12l1.43-1.27c.68-.68 1.54-1.03 2.44-1.03 1.87 0 3.39 1.52 3.39 3.38s-1.52 3.38-3.39 3.38z"/>',
  wave:     '<path d="M21 12.5c-1.5 0-2.5-1-4-1s-2.5 1-4 1-2.5-1-4-1-2.5 1-4 1V15c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1v-2.5zm0-5c-1.5 0-2.5-1-4-1s-2.5 1-4 1-2.5-1-4-1-2.5 1-4 1V10c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1V7.5z"/>',
  vortex:   '<path d="M12 6v3l4-4-4-4v3c-4.42 0-8 3.58-8 8 0 1.57.46 3.03 1.24 4.26L6.7 14.8A5.87 5.87 0 0 1 6 12c0-3.31 2.69-6 6-6zm6.76 1.74L17.3 9.2A5.9 5.9 0 0 1 18 12c0 3.31-2.69 6-6 6v-3l-4 4 4 4v-3c4.42 0 8-3.58 8-8 0-1.57-.46-3.03-1.24-4.26z"/>',
  mountain: '<path d="M14 6.5L12 3 2 21h20L14 6.5zm-2 2.6L18.9 19H9.5l2.5-9.9z"/>',
  anchor:   '<path d="M12 2a3 3 0 0 0 0 6v2H8v2h4v7.93A8 8 0 0 1 4 12H2a10 10 0 0 0 10 10 10 10 0 0 0 10-10h-2a8 8 0 0 1-7 7.93V12h4v-2h-4V8a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/>',
  key:      '<path d="M12.65 10A6 6 0 1 0 10 12.65l6.65 6.65 2.12-2.12-1.41-1.41 1.41-1.42-1.41-1.41-1.42 1.41-1.41-1.41 1.41-1.42zm-6.65 0a4 4 0 1 1 4 4 4 4 0 0 1-4-4z"/>',
};

// ── Profile icon picker ──
window._settingsProfileIcon = undefined;
window._selectProfileIcon = function(btn) {
    document.querySelectorAll('.pi-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    window._settingsProfileIcon = btn.dataset.icon;
    // Update mini preview
    var svg = document.getElementById('pi-preview-svg');
    if (svg) {
        var paths = window._PROFILE_ICONS[btn.dataset.icon] || '';
        svg.innerHTML = paths;
        svg.style.display = paths ? '' : 'none';
    }
    var hero = document.getElementById('pi-preview-hero');
    if (hero && window._settingsProfileBg) {
        hero.style.background = window._settingsProfileBg;
    }
};

// ══════════════════════════════════════════════════
// BIRTHDAY CALENDAR PICKER
// ══════════════════════════════════════════════════
(function() {
    var _calMonth = 0;
    var _calYear  = new Date().getFullYear() - 20;
    var _calSelDay   = null;
    var _calSelMonth = null;
    var _calSelYear  = null;
    var _calWithYear = false;
    var _calAnimating = false;

    var _t = function(k) { return typeof t === 'function' ? t(k) : (typeof window.t === 'function' ? window.t(k) : k); };
    var MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    var MONTHS_GEN = MONTHS.slice();
    // Lazy-init with i18n when t() becomes available
    function _initCalendarMonths() {
        if (typeof window.t === 'function') {
            var m = window.t('time.months');
            if (Array.isArray(m)) MONTHS = m;
            var g = window.t('time.monthsGen');
            if (Array.isArray(g)) MONTHS_GEN = g;
        }
    }

    window.openBirthdayPicker = function() {
        _initCalendarMonths();
        var S = window.AppState;
        var bd = S && S.user && S.user.birth_date ? S.user.birth_date : '';
        _calSelDay = null; _calSelMonth = null; _calSelYear = null;
        _calWithYear = false;
        _calMonth = 0;
        _calYear  = new Date().getFullYear() - 20;

        if (bd) {
            try {
                if (bd.startsWith('--')) {
                    var p = bd.slice(2).split('-');
                    _calSelMonth = parseInt(p[0]) - 1;
                    _calSelDay   = parseInt(p[1]);
                    _calMonth    = _calSelMonth;
                } else {
                    var parts = bd.split('-');
                    _calSelYear  = parseInt(parts[0]);
                    _calSelMonth = parseInt(parts[1]) - 1;
                    _calSelDay   = parseInt(parts[2]);
                    _calWithYear = true;
                    _calMonth    = _calSelMonth;
                    _calYear     = _calSelYear;
                }
            } catch(e) {}
        }

        var toggle = document.getElementById('bp-year-toggle');
        if (toggle) toggle.checked = _calWithYear;
        var strip = document.getElementById('bp-year-strip');
        if (strip) strip.style.display = _calWithYear ? '' : 'none';

        document.getElementById('birthday-picker').style.display = 'flex';
        requestAnimationFrame(function() {
            document.querySelector('#birthday-picker .bp-sheet').style.transform = 'translateY(0)';
        });
        _calRenderYearStrip();
        _calRender();
        _calUpdatePreview();
    };

    window.closeBirthdayPicker = function() {
        var sheet = document.querySelector('#birthday-picker .bp-sheet');
        if (sheet) sheet.style.transform = 'translateY(100%)';
        setTimeout(function() {
            document.getElementById('birthday-picker').style.display = 'none';
            if (sheet) sheet.style.transform = '';
        }, 300);
    };

    window._calToggleYear = function(on) {
        _calWithYear = on;
        var strip = document.getElementById('bp-year-strip');
        if (strip) strip.style.display = on ? '' : 'none';
        if (on) {
            if (!_calSelYear) { _calSelYear = _calYear; }
            _calRenderYearStrip();
        }
        _calUpdatePreview();
    };

    function _calRenderYearStrip() {
        var track = document.getElementById('bp-year-track');
        if (!track) return;
        var maxY = new Date().getFullYear() - 3;
        var minY = maxY - 100;
        var html = '';
        for (var y = maxY; y >= minY; y--) {
            var act = y === _calSelYear ? ' active' : '';
            html += '<button class="bp-year-chip' + act + '" onclick="window._calSelectYear(' + y + ')">' + y + '</button>';
        }
        track.innerHTML = html;
        setTimeout(function() {
            var active = track.querySelector('.active');
            if (active) active.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
        }, 60);
    }

    window._calSelectYear = function(y) {
        _calSelYear = y;
        _calYear = y;
        document.querySelectorAll('#bp-year-track .bp-year-chip').forEach(function(b) {
            b.classList.toggle('active', parseInt(b.textContent) === y);
        });
        _calUpdatePreview();
    };

    window._calPrevMonth = function() {
        if (_calAnimating) return;
        _calAnimateSlide('right', function() {
            if (--_calMonth < 0) _calMonth = 11;
            _calRender();
        });
    };

    window._calNextMonth = function() {
        if (_calAnimating) return;
        _calAnimateSlide('left', function() {
            if (++_calMonth > 11) _calMonth = 0;
            _calRender();
        });
    };

    function _calAnimateSlide(dir, cb) {
        _calAnimating = true;
        var grid = document.getElementById('bp-grid');
        if (!grid) { cb(); _calAnimating = false; return; }
        var out = dir === 'left' ? 'bp-slide-out-left' : 'bp-slide-out-right';
        var inn = dir === 'left' ? 'bp-slide-in-right' : 'bp-slide-in-left';
        grid.classList.add(out);
        setTimeout(function() {
            grid.classList.remove(out);
            cb();
            grid.classList.add(inn);
            setTimeout(function() { grid.classList.remove(inn); _calAnimating = false; }, 280);
        }, 180);
    }

    function _calRender() {
        var el = document.getElementById('bp-month-name');
        if (el) el.textContent = MONTHS[_calMonth];
        var grid = document.getElementById('bp-grid');
        if (!grid) return;

        var refYear = _calWithYear && _calSelYear ? _calSelYear : (_calYear || 2000);
        var firstDow = (new Date(refYear, _calMonth, 1).getDay() + 6) % 7; // Mon=0
        var daysInMon = new Date(refYear, _calMonth + 1, 0).getDate();
        var today = new Date();
        var isCurMon = today.getFullYear() === refYear && today.getMonth() === _calMonth;

        var html = '';
        for (var i = 0; i < firstDow; i++) html += '<div class="bp-cell bp-empty"></div>';
        for (var d = 1; d <= daysInMon; d++) {
            var cls = 'bp-cell bp-day';
            if (d === _calSelDay && _calMonth === _calSelMonth) cls += ' selected';
            if (isCurMon && d === today.getDate()) cls += ' today';
            var dow = (firstDow + d - 1) % 7;
            if (dow === 5 || dow === 6) cls += ' wknd';
            html += '<button class="' + cls + '" onclick="window._calSelectDay(' + d + ')">' + d + '</button>';
        }
        grid.innerHTML = html;
    }

    window._calSelectDay = function(d) {
        _calSelDay   = d;
        _calSelMonth = _calMonth;
        _calRender();
        _calUpdatePreview();
    };

    function _calUpdatePreview() {
        var el = document.getElementById('bp-selected-preview');
        if (!el) return;
        if (_calSelDay === null || _calSelMonth === null) { el.textContent = ''; return; }
        var text = _calSelDay + ' ' + MONTHS_GEN[_calSelMonth];
        if (_calWithYear && _calSelYear) text += ' ' + _calSelYear + ' ' + t('calendar.yearSuffix');
        el.textContent = text;
    }

    window._calApply = function() {
        if (_calSelDay === null || _calSelMonth === null) {
            window.closeBirthdayPicker();
            return;
        }
        var mm = String(_calSelMonth + 1).padStart(2, '0');
        var dd = String(_calSelDay).padStart(2, '0');
        var value, display;
        if (_calWithYear && _calSelYear) {
            value   = _calSelYear + '-' + mm + '-' + dd;
            display = dd + '.' + mm + '.' + _calSelYear;
        } else {
            value   = '--' + mm + '-' + dd;
            display = dd + '.' + mm;
        }
        var btn = document.getElementById('set-birthday-btn');
        var txt = document.getElementById('set-birthday-text');
        if (btn) {
            btn.dataset.value = value;
            btn.dataset.dirty = '1';
        }
        if (txt) txt.textContent = display;
        window.closeBirthdayPicker();
    };
})();

// ── Upload avatar from settings ──
window.uploadSettingsAvatar = async function(input) {
    if (!input.files || !input.files[0]) return;
    var formData = new FormData();
    formData.append('file', input.files[0]);
    try {
        var resp = await fetch('/api/authentication/avatar', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Upload failed');
        window.AppState.user.avatar_url = data.avatar_url;
        var av = document.getElementById('settings-avatar');
        if (av) av.innerHTML = '<img src="' + data.avatar_url + '" style="width:100%;height:100%;object-fit:cover;">';
        var sbAv = document.getElementById('sb-avatar');
        if (sbAv) sbAv.innerHTML = '<img src="' + data.avatar_url + '" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">';
    } catch(e) { alert(e.message); }
};

// ── Import key from settings ──
window.importKey = function(input) {
    if (!input.files || !input.files[0]) return;
    if (window.importPrivateKey) window.importPrivateKey(input.files[0]);
};

// ── Toggle push setting ──
window.togglePushSetting = function(enabled) {
    if (enabled && window.requestNotificationPermission) {
        window.requestNotificationPermission();
    }
};

// ── Call settings (Force TCP / Relay / Traffic Masking) ──
window._saveCallSetting = function(key, value) {
    localStorage.setItem(key, value ? 'true' : 'false');
};
window._loadCallSettings = function() {
    var keys = ['vortex_call_force_relay', 'vortex_call_force_tcp', 'vortex_call_traffic_mask'];
    var ids  = ['set-call-force-relay',    'set-call-force-tcp',    'set-call-traffic-mask'];
    for (var i = 0; i < keys.length; i++) {
        var el = document.getElementById(ids[i]);
        if (el) el.checked = localStorage.getItem(keys[i]) === 'true';
    }
};

// ── Device selection (Microphone / Speaker / Camera) ──
window._saveDeviceSetting = function(key, deviceId) {
    localStorage.setItem('vortex_device_' + key, deviceId);
};
window._getDeviceSetting = function(key) {
    return localStorage.getItem('vortex_device_' + key) || '';
};
window._refreshDeviceList = async function() {
    try {
        // Request permission first (needed to get device labels)
        await navigator.mediaDevices.getUserMedia({ audio: true, video: true }).then(function(s) {
            s.getTracks().forEach(function(t) { t.stop(); });
        }).catch(function() {
            // Try audio-only if camera denied
            return navigator.mediaDevices.getUserMedia({ audio: true }).then(function(s) {
                s.getTracks().forEach(function(t) { t.stop(); });
            });
        });
    } catch (_e) { /* ignore */ }

    try {
        var devices = await navigator.mediaDevices.enumerateDevices();
        var audioIn  = document.getElementById('set-audio-input');
        var audioOut = document.getElementById('set-audio-output');
        var videoIn  = document.getElementById('set-video-input');

        if (audioIn) {
            audioIn.textContent = '';
            var defOpt = document.createElement('option');
            defOpt.value = ''; defOpt.textContent = 'Default';
            audioIn.appendChild(defOpt);
        }
        if (audioOut) {
            audioOut.textContent = '';
            var defOpt2 = document.createElement('option');
            defOpt2.value = ''; defOpt2.textContent = 'Default';
            audioOut.appendChild(defOpt2);
        }
        if (videoIn) {
            videoIn.textContent = '';
            var defOpt3 = document.createElement('option');
            defOpt3.value = ''; defOpt3.textContent = 'Default';
            videoIn.appendChild(defOpt3);
        }

        for (var i = 0; i < devices.length; i++) {
            var d = devices[i];
            var opt = document.createElement('option');
            opt.value = d.deviceId;
            opt.textContent = d.label || (d.kind + ' ' + (i + 1));
            if (d.kind === 'audioinput' && audioIn) audioIn.appendChild(opt);
            else if (d.kind === 'audiooutput' && audioOut) audioOut.appendChild(opt);
            else if (d.kind === 'videoinput' && videoIn) videoIn.appendChild(opt);
        }

        // Restore saved selections
        if (audioIn)  audioIn.value  = window._getDeviceSetting('audioInput');
        if (audioOut) audioOut.value = window._getDeviceSetting('audioOutput');
        if (videoIn)  videoIn.value  = window._getDeviceSetting('videoInput');

        // Hide speaker select if setSinkId not supported
        if (audioOut && typeof HTMLMediaElement !== 'undefined' && !('setSinkId' in HTMLMediaElement.prototype)) {
            audioOut.parentElement.style.display = 'none';
        }
    } catch (e) {
        console.warn('[Devices] enumerate failed:', e);
    }
};
window._loadDeviceSettings = function() {
    window._refreshDeviceList();
};

// ══════════════════════════════════════════════════════════════════════════════
// PIN-код: lock screen + settings
// ══════════════════════════════════════════════════════════════════════════════
async function _hashPIN(pin) {
    var enc = new TextEncoder();
    var buf = await crypto.subtle.digest('SHA-256', enc.encode(pin));
    return Array.from(new Uint8Array(buf)).map(function(b){ return b.toString(16).padStart(2,'0'); }).join('');
}
window._setPIN = async function(pin) {
    localStorage.setItem('vortex_pin_hash', await _hashPIN(pin));
};
window._removePIN = function() {
    localStorage.removeItem('vortex_pin_hash');
};
window._verifyPIN = async function(pin) {
    var stored = localStorage.getItem('vortex_pin_hash');
    if (!stored) return true;
    return (await _hashPIN(pin)) === stored;
};
function _loadPinStatus() {
    var hasPin = !!localStorage.getItem('vortex_pin_hash');
    var notSet = document.getElementById('pin-not-set');
    var isSet  = document.getElementById('pin-is-set');
    var form   = document.getElementById('pin-setup-form');
    if (notSet) notSet.style.display = hasPin ? 'none' : '';
    if (isSet)  isSet.style.display  = hasPin ? '' : 'none';
    if (form)   form.style.display   = 'none';
}
window._pinSettingsSetup = function() {
    document.getElementById('pin-not-set').style.display = 'none';
    document.getElementById('pin-is-set').style.display  = 'none';
    document.getElementById('pin-setup-form').style.display = '';
    document.getElementById('pin-input-1').value = '';
    document.getElementById('pin-input-2').value = '';
    document.getElementById('pin-input-1').focus();
};
window._pinSettingsChange = function() { window._pinSettingsSetup(); };
window._pinSettingsCancel = function() { _loadPinStatus(); };
window._pinSettingsSave = async function() {
    var p1 = document.getElementById('pin-input-1').value.trim();
    var p2 = document.getElementById('pin-input-2').value.trim();
    if (!/^\d{4}$/.test(p1)) { alert(window.t?.('errors.pinMustBe4Digits')||'PIN must be 4 digits'); return; }
    if (p1 !== p2) { alert(window.t?.('errors.pinsDoNotMatch')||'PINs do not match'); return; }
    await window._setPIN(p1);
    alert(window.t?.('notifications.pinSet')||'PIN set');
    _loadPinStatus();
};
window._pinSettingsRemove = function() {
    if (!confirm(t('pin.removeConfirm'))) return;
    window._removePIN();
    _loadPinStatus();
};
var _pinBuffer = '';
var _pinAttempts = 0;
var _pinLocked = false;
var _pinResolve = null;
function _pinUpdateDots() {
    var dots = document.querySelectorAll('#pin-dots .pin-dot');
    for (var i = 0; i < dots.length; i++) dots[i].classList.toggle('filled', i < _pinBuffer.length);
}
function _pinShake() {
    var el = document.getElementById('pin-dots');
    el.classList.add('shake');
    setTimeout(function(){ el.classList.remove('shake'); }, 500);
}
window._pinInput = function(digit) {
    if (_pinLocked || _pinBuffer.length >= 4) return;
    _pinBuffer += String(digit);
    _pinUpdateDots();
    if (_pinBuffer.length === 4) setTimeout(function(){ _pinCheckEntry(); }, 200);
};
window._pinBackspace = function() {
    if (_pinLocked || !_pinBuffer.length) return;
    _pinBuffer = _pinBuffer.slice(0, -1);
    _pinUpdateDots();
};
window._pinClear = function() {
    if (_pinLocked) return;
    _pinBuffer = '';
    _pinUpdateDots();
};
async function _pinCheckEntry() {
    var ok = await window._verifyPIN(_pinBuffer);
    if (ok) {
        _pinAttempts = 0; _pinBuffer = ''; _pinUpdateDots();
        document.getElementById('pin-lock-error').textContent = '';
        var scr = document.getElementById('pin-lock-screen');
        scr.classList.add('pin-unlock');
        setTimeout(function(){
            scr.classList.remove('show','pin-unlock');
            if (_pinResolve) { _pinResolve(); _pinResolve = null; }
        }, 300);
    } else {
        _pinAttempts++; _pinBuffer = '';
        _pinShake();
        setTimeout(function(){ _pinUpdateDots(); }, 300);
        if (_pinAttempts >= 5) {
            _pinLocked = true;
            var errEl = document.getElementById('pin-lock-error');
            var sec = 30;
            errEl.textContent = t('pin.waitSeconds', {sec: sec});
            var iv = setInterval(function(){
                sec--;
                if (sec <= 0) { clearInterval(iv); _pinLocked = false; _pinAttempts = 0; errEl.textContent = ''; }
                else errEl.textContent = t('pin.waitSeconds', {sec: sec});
            }, 1000);
        } else {
            var e2 = document.getElementById('pin-lock-error');
            e2.textContent = t('pin.wrongPin');
            setTimeout(function(){ e2.textContent = ''; }, 2000);
        }
    }
}
window._checkPinLock = function() {
    if (!localStorage.getItem('vortex_pin_hash')) return Promise.resolve();
    _pinBuffer = ''; _pinAttempts = 0; _pinLocked = false;
    _pinUpdateDots();
    document.getElementById('pin-lock-error').textContent = '';
    document.getElementById('pin-lock-screen').classList.add('show');
    return new Promise(function(resolve) { _pinResolve = resolve; });
};
document.addEventListener('keydown', function(e) {
    var scr = document.getElementById('pin-lock-screen');
    if (!scr || !scr.classList.contains('show')) return;
    if (e.key >= '0' && e.key <= '9') { window._pinInput(parseInt(e.key)); e.preventDefault(); }
    else if (e.key === 'Backspace') { window._pinBackspace(); e.preventDefault(); }
    else if (e.key === 'Escape') { window._pinClear(); e.preventDefault(); }
});
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible' && window.AppState && window.AppState.user) {
        if (localStorage.getItem('vortex_pin_hash')) {
            _pinBuffer = ''; _pinAttempts = 0; _pinLocked = false;
            _pinUpdateDots();
            document.getElementById('pin-lock-error').textContent = '';
            document.getElementById('pin-lock-screen').classList.add('show');
        }
    }
});

// _loadPinStatus, _load2FAStatus, _highlightActiveTheme, _highlightActiveAccent
// are function declarations defined below — they are automatically on window
// and called by openSettingsSection in ux-enhancements.js.

// ══════════════════════════════════════════════════════════════════════════════
// Developer Mode
// ══════════════════════════════════════════════════════════════════════════════

(function initDevMode() {
    var enabled = localStorage.getItem('vortex_dev_mode') === '1';
    _applyDevMode(enabled);
})();

function _applyDevMode(enabled) {
    var toggle  = document.getElementById('dev-mode-toggle');
    var ideBtn  = document.getElementById('tab-btn-ide');
    if (toggle) toggle.classList.toggle('on', enabled);
    if (ideBtn) ideBtn.style.display = enabled ? '' : 'none';
    // If dev mode was disabled while IDE was open — go back to settings
    if (!enabled && typeof window.switchBottomTab === 'function') {
        var active = document.querySelector('.tab-item.active');
        if (active && active.dataset.tab === 'ide') {
            window.switchBottomTab('settings');
        }
    }
}

window.toggleDevMode = function() {
    var enabled = localStorage.getItem('vortex_dev_mode') === '1';
    enabled = !enabled;
    localStorage.setItem('vortex_dev_mode', enabled ? '1' : '0');
    _applyDevMode(enabled);
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE 1: 2FA Setup / Enable / Disable (settings)
// ══════════════════════════════════════════════════════════════════════════════

async function _load2FAStatus() {
    try {
        var resp = await window.api('GET', '/api/authentication/2fa/status');
        var setupArea   = document.getElementById('2fa-setup-area');
        var disableArea = document.getElementById('2fa-disable-area');
        var statusArea  = document.getElementById('2fa-status-area');
        if (resp.enabled) {
            if (statusArea) statusArea.style.display = 'none';
            if (setupArea)  setupArea.style.display  = 'none';
            if (disableArea) disableArea.style.display = '';
        } else {
            if (statusArea) statusArea.style.display = '';
            if (setupArea)  setupArea.style.display  = 'none';
            if (disableArea) disableArea.style.display = 'none';
        }
    } catch(e) { console.warn('2FA status check failed:', e); }
}

window.setup2FA = async function() {
    try {
        var resp = await window.api('POST', '/api/authentication/2fa/setup');
        var setupArea  = document.getElementById('2fa-setup-area');
        var statusArea = document.getElementById('2fa-status-area');
        if (statusArea) statusArea.style.display = 'none';
        if (setupArea)  setupArea.style.display  = '';

        // Show secret
        var secretEl = document.getElementById('2fa-secret-display');
        if (secretEl) secretEl.textContent = resp.secret;

        // Show QR via external API
        var qrContainer = document.getElementById('2fa-qr-container');
        if (qrContainer) {
            var qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(resp.uri);
            qrContainer.innerHTML = '<img src="' + qrUrl + '" alt="QR" style="border-radius:8px;background:white;padding:8px;">';
        }
    } catch(e) { alert(e.message); }
};

window.confirm2FA = async function() {
    var code = document.getElementById('2fa-verify-code')?.value?.trim();
    if (!code || code.length !== 6) { alert(window.t?.('errors.enter6DigitCode')||'Enter 6-digit code'); return; }
    try {
        await window.api('POST', '/api/authentication/2fa/enable', { code: code });
        alert(window.t?.('notifications.twoFaEnabled')||'2FA enabled!');
        _load2FAStatus();
    } catch(e) { alert(e.message); }
};

window.disable2FA = async function() {
    var code = document.getElementById('2fa-disable-code')?.value?.trim();
    if (!code || code.length !== 6) { alert(window.t?.('errors.enter6DigitCode')||'Enter 6-digit code'); return; }
    try {
        await window.api('POST', '/api/authentication/2fa/disable', { code: code });
        alert(window.t?.('notifications.twoFaDisabled')||'2FA disabled');
        _load2FAStatus();
    } catch(e) { alert(e.message); }
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE 2: Chat Themes & Accent Colors
// ══════════════════════════════════════════════════════════════════════════════

var _chatThemes = {
    default:  { bg: '#09090b', bg2: '#111115', bg3: '#18181d', border: '#202027', text: '#e4e4e7', text2: '#71717a', text3: '#52525b' },
    midnight: { bg: '#0d1117', bg2: '#161b22', bg3: '#21262d', border: '#30363d', text: '#c9d1d9', text2: '#8b949e', text3: '#484f58' },
    ocean:    { bg: '#0a192f', bg2: '#112240', bg3: '#1a365d', border: '#234681', text: '#ccd6f6', text2: '#8892b0', text3: '#495670' },
    forest:   { bg: '#0a1a0a', bg2: '#112211', bg3: '#1a331a', border: '#2a4a2a', text: '#d4e8d4', text2: '#8aaa8a', text3: '#4a6a4a' },
    wine:     { bg: '#1a0a0a', bg2: '#221111', bg3: '#331a1a', border: '#4a2a2a', text: '#e8d4d4', text2: '#aa8a8a', text3: '#6a4a4a' },
    purple:   { bg: '#150a1a', bg2: '#1c1122', bg3: '#261a33', border: '#3a2a4a', text: '#e0d4e8', text2: '#a08aaa', text3: '#604a6a' },
    light:    { bg: '#ffffff', bg2: '#f4f4f5', bg3: '#e4e4e7', border: '#d4d4d8', text: '#18181b', text2: '#52525b', text3: '#a1a1aa' },
};

// ── Theme Mode: dark / light / auto ──────────────────────────────────────────
window.setThemeMode = function(mode) {
    localStorage.setItem('vortex_theme_mode', mode);
    _applyThemeMode(mode);
    // Update toggle buttons
    document.querySelectorAll('.theme-mode-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.id === 'tm-' + mode);
    });
};

function _applyThemeMode(mode) {
    if (mode === 'auto') {
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        setChatTheme(prefersDark ? 'default' : 'light');
    } else if (mode === 'light') {
        setChatTheme('light');
    } else {
        // Dark mode: restore saved dark theme or use default
        var savedDark = localStorage.getItem('vortex_dark_variant') || 'default';
        setChatTheme(savedDark);
    }
}

// Listen for system theme changes (for auto mode)
try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
        if (localStorage.getItem('vortex_theme_mode') === 'auto') {
            setChatTheme(e.matches ? 'default' : 'light');
        }
    });
} catch(e) {}

window.setChatTheme = function(theme) {
    var t = _chatThemes[theme] || _chatThemes['default'];
    var root = document.documentElement;
    root.style.setProperty('--bg', t.bg);
    root.style.setProperty('--bg2', t.bg2);
    root.style.setProperty('--bg3', t.bg3);
    root.style.setProperty('--border', t.border);
    root.style.setProperty('--text', t.text);
    root.style.setProperty('--text2', t.text2);
    root.style.setProperty('--text3', t.text3);
    localStorage.setItem('vortex_theme', theme);
    // Remember dark variant for "dark" mode toggle
    if (theme !== 'light') {
        localStorage.setItem('vortex_dark_variant', theme);
    }
    if (theme === 'light') {
        document.body.setAttribute('data-theme', 'light');
    } else {
        document.body.removeAttribute('data-theme');
    }
    document.querySelectorAll('.theme-option').forEach(function(el) {
        el.classList.toggle('active', el.dataset.theme === theme);
    });
};

window.setAccentColor = function(color) {
    document.documentElement.style.setProperty('--accent', color);
    var accent2 = _lightenColor(color, 0.3);
    document.documentElement.style.setProperty('--accent2', accent2);
    localStorage.setItem('vortex_accent', color);
    document.querySelectorAll('.accent-option').forEach(function(el) {
        el.classList.toggle('active', el.dataset.accent === color);
    });
    // Update rainbow thumb
    var thumb = document.getElementById('accent-rainbow-thumb');
    if (thumb) thumb.style.background = color;
};

// Кастомный радужный color picker
window._pickRainbowColor = function(e) {
    var bar = document.getElementById('accent-rainbow-bar');
    if (!bar) return;
    var rect = bar.getBoundingClientRect();
    var x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    var pct = x / rect.width;
    var color = _hueToHex(pct * 360);
    window.setAccentColor(color);
    var thumb = document.getElementById('accent-rainbow-thumb');
    if (thumb) {
        thumb.style.left = (pct * 100) + '%';
        thumb.style.background = color;
    }
};

// Rainbow drag support
(function() {
    var dragging = false;
    document.addEventListener('mousedown', function(e) {
        if (e.target.closest('#accent-rainbow-bar')) { dragging = true; window._pickRainbowColor(e); }
    });
    document.addEventListener('mousemove', function(e) { if (dragging) window._pickRainbowColor(e); });
    document.addEventListener('mouseup', function() { dragging = false; });
    document.addEventListener('touchstart', function(e) {
        if (e.target.closest('#accent-rainbow-bar')) { dragging = true; window._pickRainbowColor(e.touches[0]); }
    }, { passive: true });
    document.addEventListener('touchmove', function(e) { if (dragging) window._pickRainbowColor(e.touches[0]); }, { passive: true });
    document.addEventListener('touchend', function() { dragging = false; });
})();

function _hueToHex(h) {
    h = h % 360;
    var s = 1, l = 0.5;
    var c = (1 - Math.abs(2 * l - 1)) * s;
    var x = c * (1 - Math.abs((h / 60) % 2 - 1));
    var m = l - c / 2;
    var r, g, b;
    if (h < 60)       { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else              { r = c; g = 0; b = x; }
    r = Math.round((r + m) * 255);
    g = Math.round((g + m) * 255);
    b = Math.round((b + m) * 255);
    return '#' + [r, g, b].map(function(v) { return v.toString(16).padStart(2, '0'); }).join('');
}

function _lightenColor(hex, amount) {
    hex = hex.replace('#', '');
    var r = parseInt(hex.substring(0,2), 16);
    var g = parseInt(hex.substring(2,4), 16);
    var b = parseInt(hex.substring(4,6), 16);
    r = Math.min(255, Math.round(r + (255 - r) * amount));
    g = Math.min(255, Math.round(g + (255 - g) * amount));
    b = Math.min(255, Math.round(b + (255 - b) * amount));
    return '#' + [r,g,b].map(function(c){ return c.toString(16).padStart(2,'0'); }).join('');
}

function _highlightActiveTheme() {
    var saved = localStorage.getItem('vortex_theme') || 'default';
    document.querySelectorAll('.theme-option').forEach(function(el) {
        el.classList.toggle('active', el.dataset.theme === saved);
    });
    // Highlight active mode button
    var mode = localStorage.getItem('vortex_theme_mode') || 'dark';
    document.querySelectorAll('.theme-mode-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.id === 'tm-' + mode);
    });
}

window._highlightLang = function() {
    var lang = localStorage.getItem('vortex_locale') || 'ru';
    document.querySelectorAll('.lang-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.dataset.lang === lang);
    });
};

function _highlightActiveAccent() {
    var saved = localStorage.getItem('vortex_accent') || '#7C3AED';
    document.querySelectorAll('.accent-option').forEach(function(el) {
        el.classList.toggle('active', el.dataset.accent === saved);
    });
}

// -- Chat Background Presets --
var _chatBgPresets = {
    none: 'none',
    stars: 'radial-gradient(ellipse at 20% 50%,rgba(124,58,237,0.15) 0%,transparent 50%),radial-gradient(ellipse at 80% 20%,rgba(59,130,246,0.1) 0%,transparent 50%),radial-gradient(1px 1px at 10% 10%,rgba(255,255,255,0.3) 50%,transparent 50%),radial-gradient(1px 1px at 20% 40%,rgba(255,255,255,0.15) 50%,transparent 50%),radial-gradient(1px 1px at 30% 70%,rgba(255,255,255,0.2) 50%,transparent 50%),radial-gradient(1px 1px at 45% 15%,rgba(255,255,255,0.1) 50%,transparent 50%),radial-gradient(1px 1px at 55% 55%,rgba(255,255,255,0.2) 50%,transparent 50%),radial-gradient(1px 1px at 60% 30%,rgba(255,255,255,0.25) 50%,transparent 50%),radial-gradient(1px 1px at 75% 65%,rgba(255,255,255,0.12) 50%,transparent 50%),radial-gradient(1px 1px at 80% 80%,rgba(255,255,255,0.15) 50%,transparent 50%),radial-gradient(1px 1px at 90% 45%,rgba(255,255,255,0.18) 50%,transparent 50%)',
    aurora: 'linear-gradient(160deg,rgba(10,10,18,0) 0%,rgba(26,10,46,0.6) 30%,rgba(10,25,47,0.6) 60%,rgba(10,26,26,0.4) 100%)',
    sunset: 'linear-gradient(180deg,rgba(26,10,46,0.6) 0%,rgba(46,26,26,0.6) 50%,rgba(26,16,8,0.5) 100%)',
    'ocean-wave': 'linear-gradient(180deg,rgba(10,25,47,0.5) 0%,rgba(13,40,71,0.5) 40%,rgba(10,58,94,0.4) 70%,rgba(10,25,47,0.5) 100%)',
    mesh: 'repeating-linear-gradient(0deg,transparent,transparent 19px,rgba(255,255,255,0.03) 19px,rgba(255,255,255,0.03) 20px),repeating-linear-gradient(90deg,transparent,transparent 19px,rgba(255,255,255,0.03) 19px,rgba(255,255,255,0.03) 20px)',
    'deep-space': 'radial-gradient(ellipse at 50% 0%,rgba(88,28,135,0.2) 0%,transparent 60%),radial-gradient(ellipse at 80% 100%,rgba(30,64,175,0.15) 0%,transparent 50%)',
    // Light backgrounds
    'light-clean': 'linear-gradient(180deg,#f8f9fa 0%,#f1f3f5 100%)',
    'light-lavender': 'linear-gradient(180deg,#f0e6ff 0%,#e8d5ff 50%,#f5eeff 100%)',
    'light-sky': 'linear-gradient(180deg,#dbeafe 0%,#bfdbfe 50%,#e0f2fe 100%)',
    'light-mint': 'linear-gradient(180deg,#d1fae5 0%,#a7f3d0 50%,#ecfdf5 100%)',
    'light-peach': 'linear-gradient(180deg,#fef3c7 0%,#fde68a 50%,#fffbeb 100%)',
    'light-rose': 'linear-gradient(180deg,#ffe4e6 0%,#fecdd3 50%,#fff1f2 100%)',
    'light-dots': 'radial-gradient(circle,rgba(124,58,237,0.08) 1px,transparent 1px)',
    'light-grid': 'repeating-linear-gradient(0deg,transparent,transparent 19px,rgba(0,0,0,0.04) 19px,rgba(0,0,0,0.04) 20px),repeating-linear-gradient(90deg,transparent,transparent 19px,rgba(0,0,0,0.04) 19px,rgba(0,0,0,0.04) 20px)',
};

window.setChatBackground = function(bgKey) {
    var mc = document.getElementById('messages-container');
    if (!mc) return;
    if (bgKey === 'none') {
        mc.style.backgroundImage = 'none';
        mc.style.backgroundSize = '';
        mc.style.backgroundPosition = '';
        mc.style.backgroundRepeat = '';
    } else if (bgKey === 'custom') {
        return;
    } else {
        var preset = _chatBgPresets[bgKey];
        if (!preset) return;
        mc.style.backgroundImage = preset;
        mc.style.backgroundSize = bgKey === 'light-dots' ? '16px 16px' : '';
        mc.style.backgroundPosition = '';
        mc.style.backgroundRepeat = '';
        // Set background color for light backgrounds
        if (bgKey.startsWith('light-')) {
            mc.style.backgroundColor = bgKey === 'light-dots' || bgKey === 'light-grid' ? '#fafafa' : '';
        } else {
            mc.style.backgroundColor = '';
        }
    }
    localStorage.setItem('vortex_chat_bg', bgKey);
    if (bgKey !== 'custom') {
        localStorage.removeItem('vortex_chat_bg_custom');
    }
    document.querySelectorAll('.bg-preview').forEach(function(el) {
        el.classList.toggle('active', el.dataset.bg === bgKey);
    });
};

window.uploadChatBackground = function(input) {
    if (!input.files || !input.files[0]) return;
    var file = input.files[0];
    if (file.size > 2 * 1024 * 1024) {
        alert(window.t?.('errors.fileTooLarge')||'File too large');
        input.value = '';
        return;
    }
    var reader = new FileReader();
    reader.onload = function(e) {
        var dataUrl = e.target.result;
        var mc = document.getElementById('messages-container');
        if (!mc) return;
        mc.style.backgroundImage = 'url(' + dataUrl + ')';
        mc.style.backgroundSize = 'cover';
        mc.style.backgroundPosition = 'center';
        mc.style.backgroundRepeat = 'no-repeat';
        localStorage.setItem('vortex_chat_bg', 'custom');
        localStorage.setItem('vortex_chat_bg_custom', dataUrl);
        document.querySelectorAll('.bg-preview').forEach(function(el) {
            el.classList.toggle('active', el.dataset.bg === 'custom');
        });
    };
    reader.readAsDataURL(file);
    input.value = '';
};

// Restore saved theme/accent/background on page load
(function() {
    // Check theme mode first (auto respects system preference)
    var themeMode = localStorage.getItem('vortex_theme_mode');
    if (themeMode === 'auto') {
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        var autoTheme = prefersDark ? (localStorage.getItem('vortex_dark_variant') || 'default') : 'light';
        var t = _chatThemes[autoTheme] || _chatThemes['default'];
        var root = document.documentElement;
        root.style.setProperty('--bg', t.bg);
        root.style.setProperty('--bg2', t.bg2);
        root.style.setProperty('--bg3', t.bg3);
        root.style.setProperty('--border', t.border);
        root.style.setProperty('--text', t.text);
        root.style.setProperty('--text2', t.text2);
        root.style.setProperty('--text3', t.text3);
        if (autoTheme === 'light') document.body.setAttribute('data-theme', 'light');
        else document.body.removeAttribute('data-theme');
    } else {
        var savedTheme = localStorage.getItem('vortex_theme');
        if (savedTheme && _chatThemes[savedTheme]) {
            var t = _chatThemes[savedTheme];
            var root = document.documentElement;
            root.style.setProperty('--bg', t.bg);
            root.style.setProperty('--bg2', t.bg2);
            root.style.setProperty('--bg3', t.bg3);
            root.style.setProperty('--border', t.border);
            root.style.setProperty('--text', t.text);
            root.style.setProperty('--text2', t.text2);
            root.style.setProperty('--text3', t.text3);
            if (savedTheme === 'light') {
                document.body.setAttribute('data-theme', 'light');
            }
        }
    }
    var savedAccent = localStorage.getItem('vortex_accent');
    if (savedAccent) {
        document.documentElement.style.setProperty('--accent', savedAccent);
        document.documentElement.style.setProperty('--accent2', _lightenColor(savedAccent, 0.3));
    }
    function _restoreChatBg() {
        var savedBg = localStorage.getItem('vortex_chat_bg');
        if (!savedBg || savedBg === 'none') return;
        var mc = document.getElementById('messages-container');
        if (!mc) return;
        if (savedBg === 'custom') {
            var customData = localStorage.getItem('vortex_chat_bg_custom');
            if (customData) {
                mc.style.backgroundImage = 'url(' + customData + ')';
                mc.style.backgroundSize = 'cover';
                mc.style.backgroundPosition = 'center';
                mc.style.backgroundRepeat = 'no-repeat';
            }
        } else if (_chatBgPresets[savedBg]) {
            mc.style.backgroundImage = _chatBgPresets[savedBg];
        }
        document.querySelectorAll('.bg-preview').forEach(function(el) {
            el.classList.toggle('active', el.dataset.bg === savedBg);
        });
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _restoreChatBg);
    } else {
        _restoreChatBg();
    }
})();

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE 3: Location Sharing
// ══════════════════════════════════════════════════════════════════════════════

window.shareLocation = function() {
    if (!navigator.geolocation) {
        alert(window.t?.('errors.geolocationNotSupported')||'Geolocation not supported');
        return;
    }
    var S = window.AppState;
    if (!S.currentRoom) {
        alert(window.t?.('errors.openChatFirst')||'Open a chat first');
        return;
    }

    navigator.geolocation.getCurrentPosition(function(pos) {
        var lat = pos.coords.latitude.toFixed(6);
        var lng = pos.coords.longitude.toFixed(6);
        var text = '\ud83d\udccd ' + t('location.location') + ': ' + lat + ', ' + lng + '\nhttps://maps.google.com/maps?q=' + lat + ',' + lng;

        var input = document.getElementById('msg-input');
        if (input) {
            input.value = text;
            if (window.sendMessage) window.sendMessage();
        }
    }, function(err) {
        if (err.code === 1) {
            var isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
            var msg = t('location.accessDenied') + '\n\n';
            if (isMac) {
                msg += t('location.macStep1') + '\n';
                msg += t('location.macStep2') + '\n';
                msg += t('location.macStep3');
            } else {
                msg += t('location.otherBrowserHint');
            }
            alert(msg);
        } else if (err.code === 2) {
            alert(window.t?.('errors.locationFailed')||'Failed to determine location');
        } else {
            alert(window.t?.('errors.locationTimeout')||'Location timeout');
        }
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 });
};

// ══════════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════════
// UNIFIED PICKER — Emoji / Stickers / GIF in one panel
// ══════════════════════════════════════════════════════════════════════════════

var _upOpen = false;
var _upCurrentTab = 'emoji';

// Bind expr-btn via addEventListener (more reliable than inline onclick)
document.addEventListener('DOMContentLoaded', function() {
    var exprBtn = document.getElementById('expr-btn');
    if (exprBtn) {
        exprBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            window.toggleUnifiedPicker();
        });
    }
});

window.closeUnifiedPicker = function() {
    var panel = document.getElementById('unified-picker');
    if (panel) { panel.classList.remove('open'); panel.style.display = 'none'; }
    _upOpen = false;
    document.removeEventListener('pointerdown', _upOutsideClick, true);
    if (window._closeEmojiPicker) window._closeEmojiPicker();
};

window.toggleUnifiedPicker = function() {
    var panel = document.getElementById('unified-picker');
    if (!panel) return;
    // Always remove stale listener first
    document.removeEventListener('pointerdown', _upOutsideClick, true);
    if (_upOpen) {
        panel.classList.remove('open');
        _upOpen = false;
        if (window._closeEmojiPicker) window._closeEmojiPicker();
    } else {
        panel.classList.add('open');
        _upOpen = true;
        window.switchPickerTab(_upCurrentTab);
        // Close on outside click — use pointerdown to avoid same-click race
        setTimeout(function() {
            document.addEventListener('pointerdown', _upOutsideClick, true);
        }, 0);
    }
};

function _upOutsideClick(e) {
    var panel = document.getElementById('unified-picker');
    var btn = document.getElementById('expr-btn');
    if (panel && !panel.contains(e.target) && btn && !btn.contains(e.target)) {
        panel.classList.remove('open');
        _upOpen = false;
        if (window._closeEmojiPicker) window._closeEmojiPicker();
        document.removeEventListener('pointerdown', _upOutsideClick, true);
    }
}

window.switchPickerTab = function(tab, btn) {
    _upCurrentTab = tab;
    document.querySelectorAll('.up-tab').forEach(function(t) { t.classList.toggle('active', t.dataset.tab === tab); });
    var content = document.getElementById('up-content');
    if (!content) return;
    content.textContent = '';

    if (tab === 'emoji') {
        // Embed emoji picker directly into content
        if (window._renderEmojiInto) {
            window._renderEmojiInto(content);
        } else {
            // Fallback: try loading the module
            import('/static/js/chat/emoji-picker.js').then(function(m) {
                if (m.renderInto) m.renderInto(content);
                else if (m.openPicker) {
                    // Use existing picker - move it into content
                    m.openPicker();
                    var picker = document.querySelector('.emoji-chat-picker');
                    if (picker) {
                        content.appendChild(picker);
                        picker.classList.add('open');
                    }
                }
            }).catch(function(e) { console.error('emoji load:', e); });
        }
    } else if (tab === 'stickers') {
        _renderStickersInPicker(content);
    } else if (tab === 'gif') {
        _renderGifsInPicker(content);
    }
};

function _renderStickersInPicker(container) {
    container.style.cssText = 'padding:8px;';
    // Load custom packs
    (async function() {
        try {
            var resp = await fetch('/api/stickers/packs', { credentials: 'include' });
            var data = resp.ok ? await resp.json() : {};
            var packs = Array.isArray(data) ? data : (data.own || []).concat(data.favorited || []);
            if (!packs.length) {
                container.innerHTML = '<div style="text-align:center;color:var(--text3);padding:32px;font-size:13px;">No sticker packs yet</div>';
                return;
            }
            packs.forEach(function(pack) {
                var stickers = pack.stickers || [];
                if (!stickers.length) return;
                var section = document.createElement('div');
                section.style.cssText = 'margin-bottom:12px;';
                var label = document.createElement('div');
                label.style.cssText = 'font-size:11px;color:var(--text3);font-weight:600;padding:4px 0;';
                label.textContent = pack.name;
                section.appendChild(label);
                var grid = document.createElement('div');
                grid.style.cssText = 'display:grid;grid-template-columns:repeat(4,1fr);gap:6px;';
                stickers.forEach(function(st) {
                    var img = document.createElement('img');
                    img.src = st.image_url;
                    img.style.cssText = 'width:100%;aspect-ratio:1;object-fit:contain;border-radius:8px;cursor:pointer;background:var(--bg3);padding:4px;box-sizing:border-box;';
                    img.addEventListener('click', function() {
                        if (window.sendStickerDirect) window.sendStickerDirect('[STICKER] img:' + st.image_url);
                        if (window.closeUnifiedPicker) window.closeUnifiedPicker();
                    });
                    grid.appendChild(img);
                });
                section.appendChild(grid);
                container.appendChild(section);
            });
        } catch(e) {
            container.innerHTML = '<div style="text-align:center;color:var(--text3);padding:24px;font-size:13px;">Failed to load</div>';
        }
    })();
}

function _renderGifsInPicker(container) {
    container.style.cssText = 'padding:8px;';
    var loading = document.createElement('div');
    loading.style.cssText = 'text-align:center;color:var(--text3);padding:24px;font-size:13px;';
    loading.textContent = (window.t?.('ui.loading')||'Loading...');
    container.appendChild(loading);
    (async function() {
        try {
            var resp = await fetch('/api/gifs/saved', { credentials: 'include' });
            var gifs = resp.ok ? await resp.json() : [];
            container.textContent = '';
            if (!gifs.length) {
                container.innerHTML = '<div style="text-align:center;color:var(--text3);padding:32px 16px;font-size:13px;">No saved GIFs.<br>Right-click a GIF in chat \u2192 "Add to GIF"</div>';
                return;
            }
            var grid = document.createElement('div');
            grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:6px;';
            gifs.forEach(function(g) {
                var wrap = document.createElement('div');
                wrap.style.cssText = 'position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:#111;cursor:pointer;';
                var img = document.createElement('img');
                img.src = g.url;
                img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
                img.addEventListener('click', function() {
                    if (window.sendGif) window.sendGif(g.url);
                    var panel = document.getElementById('unified-picker');
                    if (panel) { panel.classList.remove('open'); _upOpen = false; }
                });
                var del = document.createElement('button');
                del.style.cssText = 'position:absolute;top:3px;right:3px;background:rgba(0,0,0,.7);color:#fff;border:none;width:20px;height:20px;border-radius:50%;font-size:12px;cursor:pointer;display:none;align-items:center;justify-content:center;';
                del.textContent = '\u00D7';
                del.addEventListener('click', function(e) {
                    e.stopPropagation();
                    fetch('/api/gifs/saved/' + g.id, { method: 'DELETE', credentials: 'include', headers: { 'X-CSRF-Token': window.AppState?.csrfToken || '' } });
                    wrap.remove();
                });
                wrap.addEventListener('mouseenter', function() { del.style.display = 'flex'; });
                wrap.addEventListener('mouseleave', function() { del.style.display = 'none'; });
                wrap.append(img, del);
                grid.appendChild(wrap);
            });
            container.appendChild(grid);
        } catch(e) {
            container.innerHTML = '<div style="text-align:center;color:var(--red);padding:24px;font-size:13px;">Failed to load</div>';
        }
    })();
}

// FEATURE 4: GIF Search (Tenor API)
// ══════════════════════════════════════════════════════════════════════════════

var _gifSearchTimer = null;

window.openGifPicker = function() {
    if (!window.AppState.currentRoom) {
        window.vxAlert?.(t('chat.openChatFirst'));
        return;
    }
    window.openModal('gif-modal');
    var results = document.getElementById('gif-results');
    if (!results) return;
    results.textContent = '';
    var loading = document.createElement('div');
    loading.style.cssText = 'text-align:center;color:var(--text3);padding:24px;font-size:13px;';
    loading.textContent = (window.t?.('ui.loading')||'Loading...');
    results.appendChild(loading);

    (async function() {
        try {
            var resp = await fetch('/api/gifs/saved', { credentials: 'include' });
            var gifs = resp.ok ? await resp.json() : [];
            results.textContent = '';
            if (!gifs.length) {
                var empty = document.createElement('div');
                empty.style.cssText = 'text-align:center;color:var(--text3);padding:32px 16px;font-size:13px;';
                empty.textContent = 'No saved GIFs yet. Right-click a GIF in chat \u2192 "Add to GIF".';
                results.appendChild(empty);
                return;
            }
            var grid = document.createElement('div');
            grid.style.cssText = 'display:grid;grid-template-columns:repeat(3,1fr);gap:6px;';
            gifs.forEach(function(g) {
                var wrap = document.createElement('div');
                wrap.style.cssText = 'position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:#111;cursor:pointer;';
                var img = document.createElement('img');
                img.src = g.url;
                img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
                img.addEventListener('click', function() { window.sendGif(g.url); });
                // Delete button
                var del = document.createElement('button');
                del.style.cssText = 'position:absolute;top:4px;right:4px;background:rgba(0,0,0,.7);color:#fff;border:none;width:22px;height:22px;border-radius:50%;font-size:14px;cursor:pointer;display:none;align-items:center;justify-content:center;';
                del.textContent = '\u00D7';
                del.addEventListener('click', function(e) {
                    e.stopPropagation();
                    fetch('/api/gifs/saved/' + g.id, { method: 'DELETE', credentials: 'include', headers: { 'X-CSRF-Token': window.AppState?.csrfToken || '' } });
                    wrap.remove();
                });
                wrap.addEventListener('mouseenter', function() { del.style.display = 'flex'; });
                wrap.addEventListener('mouseleave', function() { del.style.display = 'none'; });
                wrap.append(img, del);
                grid.appendChild(wrap);
            });
            results.appendChild(grid);
        } catch(e) {
            console.error('Load saved GIFs error:', e);
            results.textContent = '';
            var err = document.createElement('div');
            err.style.cssText = 'text-align:center;color:var(--red);padding:24px;font-size:13px;';
            err.textContent = (window.t?.('gifs.failedToLoad')||'Failed to load GIFs');
            results.appendChild(err);
        }
    })();
};

window.searchGifs = function(query) {
    clearTimeout(_gifSearchTimer);
    var el = document.getElementById('gif-results');
    if (!query || !query.trim()) {
        if (el) el.innerHTML = '<div style="padding:16px;color:var(--text2);text-align:center;">' + t('search.enterQuery') + '</div>';
        return;
    }
    _gifSearchTimer = setTimeout(async function() {
        if (el) el.innerHTML = '<div style="padding:16px;color:var(--text2);text-align:center;">' + t('search.searching') + '</div>';
        try {
            var key = 'AIzaSyDvT6aTBbn1fJWEAqEz1Kht2xQN_pjUib0';
            var resp = await fetch('https://tenor.googleapis.com/v2/search?q=' + encodeURIComponent(query) + '&key=' + key + '&limit=20&media_filter=gif');
            var data = await resp.json();
            var results = data.results || [];
            if (results.length === 0) {
                el.innerHTML = '<div style="padding:16px;color:var(--text2);text-align:center;">' + t('search.nothingFound') + '</div>';
                return;
            }
            el.innerHTML = results.map(function(gif) {
                var preview = (gif.media_formats && (gif.media_formats.nanogif || gif.media_formats.tinygif || {}).url) || '';
                var full = (gif.media_formats && (gif.media_formats.gif || gif.media_formats.tinygif || {}).url) || preview;
                return '<img src="' + preview + '" data-full="' + full + '" onclick="sendGif(\'' + full.replace(/'/g, "\\'") + '\')" ' +
                       'style="width:calc(50% - 4px);cursor:pointer;border-radius:4px;object-fit:cover;max-height:150px;">';
            }).join('');
        } catch(e) {
            if (el) el.innerHTML = '<div style="padding:16px;color:var(--red);text-align:center;">' + t('search.searchError', {message: e.message}) + '</div>';
        }
    }, 500);
};

window.sendGif = function(url) {
    window.closeModal('gif-modal');
    if (window.closeUnifiedPicker) window.closeUnifiedPicker();
    var input = document.getElementById('msg-input');
    if (input) {
        input.value = '[GIF] ' + url;
        if (window.sendMessage) window.sendMessage();
    }
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE 5: Share Profile Link
// ══════════════════════════════════════════════════════════════════════════════

window.copyProfileLink = function() {
    var u = window.AppState.user;
    if (!u) return;
    var link = location.origin + '?contact=' + encodeURIComponent(u.username);
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function() {
            window.showToast?.(t('common.linkCopied'), 'success');
        }).catch(function() {
            window.vxAlert(t('common.copyLink'), { token: link });
        });
    } else {
        window.vxAlert(t('common.copyLink'), { token: link });
    }
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Sticker Picker
// ══════════════════════════════════════════════════════════════════════════════

// Animated sticker definitions (vortex pack)
var ANIMATED_STICKERS = [
    { name: 'wave',     emoji: '\u{1F44B}', label: t('stickers.wave') },
    { name: 'heart',    emoji: '\u{2764}\u{FE0F}', label: t('stickers.heart') },
    { name: 'fire',     emoji: '\u{1F525}', label: t('stickers.fire') },
    { name: 'laugh',    emoji: '\u{1F602}', label: t('stickers.laugh') },
    { name: 'cry',      emoji: '\u{1F62D}', label: t('stickers.cry') },
    { name: 'thumbsup', emoji: '\u{1F44D}', label: t('stickers.thumbsUp') },
    { name: 'party',    emoji: '\u{1F389}', label: t('stickers.party') },
    { name: 'rocket',   emoji: '\u{1F680}', label: t('stickers.rocket') },
    { name: 'star',     emoji: '\u{2B50}',  label: t('stickers.star') },
    { name: 'cool',     emoji: '\u{1F60E}', label: t('stickers.cool') },
    { name: 'love',     emoji: '\u{1F970}', label: t('stickers.love') },
    { name: 'clap',     emoji: '\u{1F44F}', label: t('stickers.applause') },
    { name: 'think',    emoji: '\u{1F914}', label: t('stickers.thinking') },
    { name: 'scared',   emoji: '\u{1F631}', label: t('stickers.fear') },
    { name: 'angry',    emoji: '\u{1F621}', label: t('stickers.anger') },
    { name: 'sleep',    emoji: '\u{1F634}', label: t('stickers.sleep') },
    { name: 'money',    emoji: '\u{1F911}', label: t('stickers.money') },
    { name: 'ghost',    emoji: '\u{1F47B}', label: t('stickers.ghost') },
    { name: 'hundred',  emoji: '\u{1F4AF}', label: '100' },
    { name: 'eyes',     emoji: '\u{1F440}', label: t('stickers.eyes') }
];

// Classic emoji sticker packs
var STICKER_PACKS = {
    emotions: ['\u{1F600}','\u{1F602}','\u{1F923}','\u{1F60D}','\u{1F970}','\u{1F618}','\u{1F60E}','\u{1F929}','\u{1F624}','\u{1F621}','\u{1F622}','\u{1F62D}','\u{1F97A}','\u{1F631}','\u{1F92E}','\u{1F480}','\u{1F47B}','\u{1F921}','\u{1F608}','\u{1F47F}','\u{1F4A9}','\u{1F916}','\u{1F47D}','\u{1F383}'],
    animals: ['\u{1F436}','\u{1F431}','\u{1F42D}','\u{1F439}','\u{1F430}','\u{1F98A}','\u{1F43B}','\u{1F43C}','\u{1F428}','\u{1F42F}','\u{1F981}','\u{1F42E}','\u{1F437}','\u{1F438}','\u{1F435}','\u{1F984}','\u{1F41D}','\u{1F98B}','\u{1F422}','\u{1F40D}','\u{1F98E}','\u{1F988}','\u{1F419}','\u{1F980}'],
    food: ['\u{1F34E}','\u{1F355}','\u{1F354}','\u{1F32E}','\u{1F35F}','\u{1F37F}','\u{1F369}','\u{1F382}','\u{1F370}','\u{1F36B}','\u{1F36C}','\u{2615}','\u{1F37A}','\u{1F377}','\u{1F964}','\u{1F349}','\u{1F347}','\u{1F353}','\u{1F951}','\u{1F33D}','\u{1F955}','\u{1F346}','\u{1F966}','\u{1F9C0}'],
    activities: ['\u{26BD}','\u{1F3C0}','\u{1F3BE}','\u{1F3C8}','\u{1F3AF}','\u{1F3AE}','\u{1F3B2}','\u{1F3AD}','\u{1F3A8}','\u{1F3B5}','\u{1F3B8}','\u{1F3B9}','\u{1F3C6}','\u{1F947}','\u{1F3AA}','\u{1F3A0}','\u{1F3C4}','\u{1F6B4}','\u{26F7}','\u{1F3CA}','\u{1F9D7}','\u{1F938}','\u{1F3CB}','\u{1F93A}'],
    objects: ['\u{2764}','\u{1F494}','\u{1F495}','\u{1F496}','\u{2728}','\u{2B50}','\u{1F31F}','\u{1F4AB}','\u{1F525}','\u{1F4A7}','\u{1F308}','\u{2600}','\u{1F319}','\u{26A1}','\u{1F48E}','\u{1F381}','\u{1F388}','\u{1F380}','\u{1F3E0}','\u{1F680}','\u{2708}','\u{1F6F8}','\u{1F4BB}','\u{1F4F1}'],
};

window.openStickerPicker = function() {
    if (window.openModal) window.openModal('sticker-modal');
    window.showStickerCategory('my_stickers', document.querySelector('#sticker-modal .settings-tab'));
};

window.showStickerCategory = function(cat, btn) {
    document.querySelectorAll('#sticker-modal .settings-tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    var grid = document.getElementById('sticker-grid');
    if (!grid) return;

    if (cat === 'my_stickers') {
        // Render user's custom stickers (VXS1 format)
        grid.className = '';
        grid.style.cssText = 'display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:12px;max-height:280px;overflow-y:auto;';
        grid.textContent = '';
        var stickers = typeof window.getMyStickers === 'function' ? window.getMyStickers() : [];
        if (stickers.length === 0) {
            var empty = document.createElement('div');
            empty.style.cssText = 'grid-column:1/-1;text-align:center;padding:24px;color:var(--text3);font-size:13px;';
            empty.textContent = t('stickers.noStickersHint');
            grid.appendChild(empty);
        } else {
            stickers.forEach(function(s) {
                var item = document.createElement('div');
                item.style.cssText = 'cursor:pointer;border-radius:8px;overflow:hidden;aspect-ratio:1;display:flex;align-items:center;justify-content:center;background:var(--bg3);position:relative;';
                if (s.preview_url) {
                    var img = document.createElement('img');
                    img.src = s.preview_url;
                    img.style.cssText = 'width:100%;height:100%;object-fit:contain;';
                    img.loading = 'lazy';
                    item.appendChild(img);
                } else {
                    item.textContent = s.emoji || s.name?.charAt(0) || '?';
                    item.style.fontSize = '32px';
                }
                item.addEventListener('click', function() {
                    window.sendMySticker?.(s.id);
                    window.closeModal?.('sticker-modal');
                });
                // Long press to delete
                var holdTimer = null;
                item.addEventListener('touchstart', function() {
                    holdTimer = setTimeout(function() {
                        if (confirm(t('stickers.deleteConfirm'))) {
                            window.removeMySticker?.(s.id);
                            window.showStickerCategory('my_stickers', btn);
                        }
                    }, 600);
                }, { passive: true });
                item.addEventListener('touchend', function() { clearTimeout(holdTimer); });
                grid.appendChild(item);
            });
        }
        // Add sticker button
        var addBtn = document.createElement('div');
        addBtn.style.cssText = 'cursor:pointer;border-radius:8px;aspect-ratio:1;display:flex;align-items:center;justify-content:center;background:var(--bg3);border:2px dashed var(--border);color:var(--text3);font-size:24px;';
        addBtn.textContent = '+';
        addBtn.title = t('stickers.addSticker');
        var addInput = document.createElement('input');
        addInput.type = 'file';
        addInput.accept = 'image/*';
        addInput.style.display = 'none';
        addInput.addEventListener('change', function() {
            if (addInput.files[0]) {
                window.addToMyStickers?.(addInput.files[0]);
                setTimeout(function() { window.showStickerCategory('my_stickers', btn); }, 500);
            }
        });
        addBtn.addEventListener('click', function() { addInput.click(); });
        addBtn.appendChild(addInput);
        grid.appendChild(addBtn);
        return;
    }

    if (cat === 'animated') {
        // Render animated sticker grid (4 columns)
        grid.className = 'sticker-grid-animated';
        grid.style.cssText = '';
        grid.innerHTML = ANIMATED_STICKERS.map(function(s) {
            return '<button class="sticker-preview" onclick="sendAnimatedSticker(\'' + s.name + '\')" title="' + s.label + '">' +
                '<span class="animated-sticker sticker-' + s.name + '">' + s.emoji + '</span>' +
                '</button>';
        }).join('');
    } else {
        // Render classic emoji grid (5 columns)
        grid.className = '';
        grid.style.cssText = 'display:grid;grid-template-columns:repeat(5,1fr);gap:4px;max-height:250px;overflow-y:auto;';
        var stickers = STICKER_PACKS[cat] || [];
        grid.innerHTML = stickers.map(function(s) {
            return '<div style="font-size:36px;text-align:center;cursor:pointer;padding:8px;border-radius:8px;transition:background 0.1s;" ' +
                'onmouseover="this.style.background=\'var(--bg3)\'" onmouseout="this.style.background=\'\'" ' +
                'onclick="sendSticker(\'' + s + '\')">' + s + '</div>';
        }).join('');
    }
};

window.sendAnimatedSticker = function(name) {
    if (window.closeModal) window.closeModal('sticker-modal');
    if (window.closeUnifiedPicker) window.closeUnifiedPicker();
    if (window.sendStickerDirect) window.sendStickerDirect('[STICKER] vortex:' + name);
};

window.sendSticker = function(emoji) {
    if (window.closeModal) window.closeModal('sticker-modal');
    if (window.closeUnifiedPicker) window.closeUnifiedPicker();
    if (window.sendStickerDirect) window.sendStickerDirect('[STICKER] ' + emoji);
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Custom Sticker Packs (Manager + Enhanced Picker)
// ══════════════════════════════════════════════════════════════════════════════

// Cached custom packs for the picker
window._customStickerPacks = [];

// ── Sticker Manager tab switching ──
window.switchStickerMgrTab = function(tab, btn) {
    document.querySelectorAll('.sticker-mgr-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.sticker-mgr-section').forEach(function(s) { s.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    var el = document.getElementById('sticker-mgr-' + tab);
    if (el) el.classList.add('active');
    if (tab === 'my') loadMyPacks();
    if (tab === 'catalog') loadCatalogPacks();
};

window.toggleStickerCreateForm = function() {
    var form = document.getElementById('sticker-create-form');
    if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
};

// ── CSRF helper ──
function _stickerHeaders(isJSON) {
    var headers = {};
    var S = window.AppState;
    if (S && S.csrfToken) headers['X-CSRF-Token'] = S.csrfToken;
    if (isJSON) headers['Content-Type'] = 'application/json';
    return headers;
}

// ── HTML escape ──
function _sesc(s) {
    var d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

// ── Load user's own + favorited packs ──
window.loadMyPacks = async function() {
    var list = document.getElementById('sticker-my-packs-list');
    if (!list) return;
    try {
        var resp = await fetch('/api/stickers/packs', { credentials: 'include', headers: _stickerHeaders(false) });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var data = await resp.json();
        var packs = Array.isArray(data) ? data : (data.own || []).concat(data.favorited || []);
        window._customStickerPacks = packs;
        _renderMyPacks(packs, list);
    } catch(e) {
        list.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('stickers.failedToLoadPacks') + '</div>';
        console.warn('loadMyPacks error:', e);
    }
};

function _renderMyPacks(packs, container) {
    if (!packs || packs.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('stickers.noPacksYet') + '</div>';
        return;
    }
    var S = window.AppState;
    var myId = S && S.user ? (S.user.user_id || S.user.id) : null;
    container.innerHTML = packs.map(function(pack) {
        var isOwner = pack.creator_id === myId;
        var stickerCount = (pack.stickers && pack.stickers.length) || 0;
        var coverHtml = pack.cover_url
            ? '<img src="' + _sesc(pack.cover_url) + '" class="sticker-pack-cover">'
            : '<div class="sticker-pack-cover sticker-pack-cover--empty">📦</div>';
        var actions = '';
        if (isOwner) {
            actions = '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();deleteStickerPack(\'' + pack.id + '\')" title="' + t('common.delete') + '" style="color:var(--red);padding:4px 8px;font-size:11px;">' + t('common.delete') + '</button>';
        } else {
            actions = '<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation();unfavoritePack(\'' + pack.id + '\')" title="' + t('common.remove') + '" style="padding:4px 8px;font-size:11px;">' + t('common.remove') + '</button>';
        }
        return '<div class="sticker-pack-card" onclick="togglePackExpand(this,\'' + pack.id + '\',' + isOwner + ')">' +
            '<div class="sticker-pack-card-header">' +
                coverHtml +
                '<div class="sticker-pack-card-info">' +
                    '<div class="sticker-pack-card-name">' + _sesc(pack.name) + '</div>' +
                    '<div class="sticker-pack-card-meta">' + t('stickers.stickerCount', {count: stickerCount}) + '</div>' +
                '</div>' +
                '<div class="sticker-pack-card-actions">' + actions + '</div>' +
            '</div>' +
            '<div class="sticker-pack-expand" style="display:none;"></div>' +
        '</div>';
    }).join('');
}

function _pluralRu(n) {
    var m = n % 10, mm = n % 100;
    if (m === 1 && mm !== 11) return '';
    if (m >= 2 && m <= 4 && (mm < 12 || mm > 14)) return 's';
    return 's';
}

// ── Open fullscreen pack editor ──
window.togglePackExpand = function(cardEl, packId, isOwner) {
    window.openPackEditor(packId, isOwner);
};

window.openPackEditor = async function(packId, isOwner) {
    document.getElementById('spe-root')?.remove();
    var root = document.createElement('div');
    root.id = 'spe-root'; root.className = 'spe-root';

    // Loading state
    // NOTE: all innerHTML below is static trusted HTML (SVG icons, layout strings). No user data is interpolated unsafely.
    root.innerHTML = '<div class="spe-loading">Loading...</div>';
    document.body.appendChild(root);

    var pack;
    try {
        var resp = await fetch('/api/stickers/packs/' + packId, { credentials: 'include', headers: _stickerHeaders(false) });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var _data = await resp.json();
        pack = _data.pack || _data; // unwrap envelope
    } catch(e) {
        root.innerHTML = '<div class="spe-loading">Error loading pack</div>';
        setTimeout(function() { root.remove(); }, 1500);
        return;
    }

    isOwner = String(pack.creator_id) === String(window.AppState?.user?.user_id || window.AppState?.user?.id || '');
    var stickers = pack.stickers || [];

    function _render() {
        var coverSrc = pack.cover_url || '';
        root.innerHTML = '';

        // Header
        var header = document.createElement('div'); header.className = 'spe-header';
        var backBtn = document.createElement('button'); backBtn.className = 'spe-hdr-btn';
        backBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>';
        backBtn.addEventListener('click', function() { root.remove(); loadMyPacks(); });
        var title = document.createElement('div'); title.className = 'spe-title';
        title.textContent = pack.name;
        header.append(backBtn, title);
        if (isOwner) {
            var delBtn = document.createElement('button'); delBtn.className = 'spe-hdr-btn spe-hdr-del';
            delBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>';
            delBtn.addEventListener('click', async function() {
                if (!confirm((window.t?.('stickers.deleteConfirm')||'Delete this sticker pack?'))) return;
                await fetch('/api/stickers/packs/' + packId, { method: 'DELETE', credentials: 'include', headers: _stickerHeaders(false) });
                root.remove(); loadMyPacks();
            });
            header.appendChild(delBtn);
        }
        root.appendChild(header);

        // Cover + info
        var infoBox = document.createElement('div'); infoBox.className = 'spe-info';
        var coverEl = document.createElement('div'); coverEl.className = 'spe-cover';
        if (coverSrc) {
            var img = document.createElement('img'); img.src = coverSrc; img.className = 'spe-cover-img';
            coverEl.appendChild(img);
        } else {
            coverEl.textContent = '\u{1F4E6}';
            coverEl.classList.add('spe-cover-empty');
        }
        if (isOwner) {
            var coverBtn = document.createElement('button'); coverBtn.className = 'spe-cover-edit';
            coverBtn.textContent = '+';
            coverBtn.addEventListener('click', function() {
                var inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*';
                inp.addEventListener('change', async function() {
                    if (!inp.files?.[0]) return;
                    // Upload as first sticker, then set cover
                    var fd = new FormData(); fd.append('file', inp.files[0]);
                    var h = {}; if (window.AppState?.csrfToken) h['X-CSRF-Token'] = window.AppState.csrfToken;
                    var r = await fetch('/api/stickers/packs/' + packId + '/stickers', { method: 'POST', credentials: 'include', headers: h, body: fd });
                    if (r.ok) {
                        var _coverData = await r.json();
                        var _st = _coverData.sticker || _coverData;
                        pack.cover_url = _st.image_url;
                        await fetch('/api/stickers/packs/' + packId, { method: 'PUT', credentials: 'include', headers: _stickerHeaders(true), body: JSON.stringify({ cover_url: st.image_url }) });
                        window.openPackEditor(packId, isOwner);
                    }
                }); inp.click();
            });
            coverEl.appendChild(coverBtn);
        }
        var details = document.createElement('div'); details.className = 'spe-details';

        if (isOwner) {
            var nameInp = document.createElement('input'); nameInp.className = 'spe-name-input';
            nameInp.value = pack.name; nameInp.placeholder = 'Pack name';
            nameInp.addEventListener('change', async function() {
                var v = nameInp.value.trim(); if (!v) return;
                await fetch('/api/stickers/packs/' + packId, { method: 'PUT', credentials: 'include', headers: _stickerHeaders(true), body: JSON.stringify({ name: v }) });
                pack.name = v; title.textContent = v;
            });
            var descInp = document.createElement('input'); descInp.className = 'spe-desc-input';
            descInp.value = pack.description || ''; descInp.placeholder = 'Description...';
            descInp.addEventListener('change', async function() {
                await fetch('/api/stickers/packs/' + packId, { method: 'PUT', credentials: 'include', headers: _stickerHeaders(true), body: JSON.stringify({ description: descInp.value.trim() }) });
            });
            details.append(nameInp, descInp);
        } else {
            var nameEl = document.createElement('div'); nameEl.className = 'spe-name'; nameEl.textContent = pack.name;
            var descEl = document.createElement('div'); descEl.className = 'spe-desc'; descEl.textContent = pack.description || '';
            details.append(nameEl, descEl);
        }

        var meta = document.createElement('div'); meta.className = 'spe-meta';
        meta.textContent = stickers.length + ' sticker' + (stickers.length !== 1 ? 's' : '') + ' \u00B7 ' + (pack.is_public ? 'Public' : 'Private');
        details.appendChild(meta);

        // Public toggle for owner
        if (isOwner) {
            var pubRow = document.createElement('div'); pubRow.className = 'spe-pub-row';
            var pubLabel = document.createElement('span'); pubLabel.textContent = (window.t?.('videoEditor.publicInCatalog')||'Public in catalog');
            var pubToggle = document.createElement('button');
            pubToggle.className = 'spe-toggle' + (pack.is_public ? ' active' : '');
            pubToggle.innerHTML = '<span class="spe-toggle-knob"></span>';
            pubToggle.addEventListener('click', async function() {
                var newVal = !pack.is_public;
                await fetch('/api/stickers/packs/' + packId, { method: 'PUT', credentials: 'include', headers: _stickerHeaders(true), body: JSON.stringify({ is_public: newVal }) });
                pack.is_public = newVal;
                pubToggle.classList.toggle('active', newVal);
                meta.textContent = stickers.length + ' sticker' + (stickers.length !== 1 ? 's' : '') + ' \u00B7 ' + (newVal ? 'Public' : 'Private');
            });
            pubRow.append(pubLabel, pubToggle); details.appendChild(pubRow);
        }

        infoBox.append(coverEl, details);
        root.appendChild(infoBox);

        // Stickers grid
        var gridLabel = document.createElement('div'); gridLabel.className = 'spe-section-label';
        gridLabel.textContent = (window.t?.('ui.stickers')||'Stickers');
        root.appendChild(gridLabel);

        var grid = document.createElement('div'); grid.className = 'spe-grid';
        stickers.forEach(function(st) {
            var wrap = document.createElement('div'); wrap.className = 'spe-sticker';
            var img = document.createElement('img'); img.src = st.image_url; img.className = 'spe-sticker-img';
            wrap.appendChild(img);
            if (isOwner) {
                var del = document.createElement('button'); del.className = 'spe-sticker-del';
                del.innerHTML = '&times;';
                del.addEventListener('click', async function(e) {
                    e.stopPropagation();
                    await fetch('/api/stickers/packs/' + packId + '/stickers/' + st.id, { method: 'DELETE', credentials: 'include', headers: _stickerHeaders(false) });
                    stickers = stickers.filter(function(s) { return s.id !== st.id; });
                    pack.stickers = stickers;
                    _render();
                });
                wrap.appendChild(del);
            }
            grid.appendChild(wrap);
        });

        // Upload button
        if (isOwner) {
            var addBtn = document.createElement('div'); addBtn.className = 'spe-sticker spe-sticker-add';
            addBtn.innerHTML = '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>';
            addBtn.addEventListener('click', function() {
                var inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/png,image/webp,image/gif,image/jpeg';
                inp.multiple = true;
                inp.addEventListener('change', async function() {
                    if (!inp.files?.length) return;
                    for (var i = 0; i < inp.files.length; i++) {
                        var fd = new FormData(); fd.append('file', inp.files[i]);
                        var h = {}; if (window.AppState?.csrfToken) h['X-CSRF-Token'] = window.AppState.csrfToken;
                        var r = await fetch('/api/stickers/packs/' + packId + '/stickers', { method: 'POST', credentials: 'include', headers: h, body: fd });
                        if (r.ok) { var _stData = await r.json(); stickers.push(_stData.sticker || _stData); pack.stickers = stickers; }
                    }
                    _render();
                }); inp.click();
            });
            grid.appendChild(addBtn);

            // Drag and drop zone
            grid.addEventListener('dragover', function(e) { e.preventDefault(); grid.classList.add('spe-dragover'); });
            grid.addEventListener('dragleave', function() { grid.classList.remove('spe-dragover'); });
            grid.addEventListener('drop', async function(e) {
                e.preventDefault(); grid.classList.remove('spe-dragover');
                var files = e.dataTransfer?.files;
                if (!files?.length) return;
                for (var i = 0; i < files.length; i++) {
                    if (!files[i].type.startsWith('image/')) continue;
                    var fd = new FormData(); fd.append('file', files[i]);
                    var h = {}; if (window.AppState?.csrfToken) h['X-CSRF-Token'] = window.AppState.csrfToken;
                    var r = await fetch('/api/stickers/packs/' + packId + '/stickers', { method: 'POST', credentials: 'include', headers: h, body: fd });
                    if (r.ok) { var _stData = await r.json(); stickers.push(_stData.sticker || _stData); pack.stickers = stickers; }
                }
                _render();
            });
        }

        root.appendChild(grid);

        if (stickers.length === 0) {
            var empty = document.createElement('div'); empty.className = 'spe-empty';
            empty.textContent = isOwner ? 'No stickers yet. Click + or drag images to add.' : (window.t?.('stickers.packEmpty')||'Pack is empty');
            root.appendChild(empty);
        }
    }

    _render();
};

// ── Create pack ──
window.createStickerPack = async function() {
    var name = document.getElementById('sticker-pack-name')?.value?.trim();
    if (!name) return;
    var desc = document.getElementById('sticker-pack-desc')?.value?.trim() || '';
    try {
        var resp = await fetch('/api/stickers/packs', {
            method: 'POST',
            credentials: 'include',
            headers: _stickerHeaders(true),
            body: JSON.stringify({ name: name, description: desc, is_public: false })
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var data = await resp.json();
        var newPackId = data.pack ? data.pack.id : data.id;
        document.getElementById('sticker-pack-name').value = '';
        document.getElementById('sticker-pack-desc').value = '';
        toggleStickerCreateForm();
        // Open the new pack in fullscreen editor immediately
        if (newPackId) window.openPackEditor(newPackId, true);
        else loadMyPacks();
    } catch(e) {
        console.warn('createStickerPack error:', e);
        alert(window.t?.('stickers.failedToCreatePack')||'Failed to create pack');
    }
};

// ── Delete pack ──
window.deleteStickerPack = async function(packId) {
    if (!confirm(t('stickers.deletePackConfirm'))) return;
    try {
        await fetch('/api/stickers/packs/' + packId, {
            method: 'DELETE',
            credentials: 'include',
            headers: _stickerHeaders(false)
        });
        loadMyPacks();
    } catch(e) { console.warn('deleteStickerPack error:', e); }
};

// ── Upload sticker to pack ──
window.triggerStickerUpload = function(packId) {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/png,image/webp,image/gif,image/jpeg';
    input.onchange = function() {
        if (!input.files || !input.files[0]) return;
        uploadStickerFile(packId, input.files[0]);
    };
    input.click();
};

window.uploadStickerFile = async function(packId, file) {
    var formData = new FormData();
    formData.append('file', file);
    try {
        var headers = {};
        var S = window.AppState;
        if (S && S.csrfToken) headers['X-CSRF-Token'] = S.csrfToken;
        var resp = await fetch('/api/stickers/packs/' + packId + '/stickers', {
            method: 'POST',
            credentials: 'include',
            headers: headers,
            body: formData
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        loadMyPacks();
    } catch(e) {
        console.warn('uploadStickerFile error:', e);
        alert(window.t?.('stickers.failedToLoadSticker')||'Failed to load sticker');
    }
};

// ── Delete sticker from pack ──
window.deleteStickerFromPack = async function(packId, stickerId) {
    try {
        await fetch('/api/stickers/packs/' + packId + '/stickers/' + stickerId, {
            method: 'DELETE',
            credentials: 'include',
            headers: _stickerHeaders(false)
        });
        loadMyPacks();
    } catch(e) { console.warn('deleteStickerFromPack error:', e); }
};

// ── Favorite / unfavorite ──
window.favoritePack = async function(packId) {
    try {
        await fetch('/api/stickers/packs/' + packId + '/favorite', {
            method: 'POST',
            credentials: 'include',
            headers: _stickerHeaders(false)
        });
        loadCatalogPacks();
        loadMyPacks();
    } catch(e) { console.warn('favoritePack error:', e); }
};

window.unfavoritePack = async function(packId) {
    try {
        await fetch('/api/stickers/packs/' + packId + '/favorite', {
            method: 'DELETE',
            credentials: 'include',
            headers: _stickerHeaders(false)
        });
        loadMyPacks();
    } catch(e) { console.warn('unfavoritePack error:', e); }
};

// ── Catalog (public packs) ──
window.loadCatalogPacks = async function() {
    var list = document.getElementById('sticker-catalog-list');
    if (!list) return;
    try {
        var resp = await fetch('/api/stickers/packs/public', { credentials: 'include', headers: _stickerHeaders(false) });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var packs = await resp.json();
        _renderCatalogPacks(packs, list);
    } catch(e) {
        list.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('stickers.failedToLoadCatalog') + '</div>';
        console.warn('loadCatalogPacks error:', e);
    }
};

function _renderCatalogPacks(packs, container) {
    if (!packs || packs.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('stickers.catalogEmpty') + '</div>';
        return;
    }
    // Determine which packs user already has
    var ownedIds = {};
    (window._customStickerPacks || []).forEach(function(p) { ownedIds[p.id] = true; });

    container.innerHTML = packs.map(function(pack) {
        var stickerCount = (pack.stickers && pack.stickers.length) || 0;
        var coverHtml = pack.cover_url
            ? '<img src="' + _sesc(pack.cover_url) + '" class="sticker-pack-cover">'
            : '<div class="sticker-pack-cover sticker-pack-cover--empty">📦</div>';
        var addBtn = ownedIds[pack.id]
            ? '<span style="font-size:11px;color:var(--green);">' + t('common.added') + '</span>'
            : '<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();favoritePack(\'' + pack.id + '\')" style="padding:4px 10px;font-size:11px;">' + t('common.add') + '</button>';
        return '<div class="sticker-pack-card">' +
            '<div class="sticker-pack-card-header">' +
                coverHtml +
                '<div class="sticker-pack-card-info">' +
                    '<div class="sticker-pack-card-name">' + _sesc(pack.name) + '</div>' +
                    '<div class="sticker-pack-card-meta">' + t('stickers.stickerCount', {count: stickerCount}) +
                        (pack.description ? ' &mdash; ' + _sesc(pack.description) : '') + '</div>' +
                '</div>' +
                '<div class="sticker-pack-card-actions">' + addBtn + '</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

// ── Enhanced sticker picker: inject custom pack tabs ──
window._loadCustomPackTabs = async function() {
    var tabsContainer = document.getElementById('custom-pack-tabs');
    if (!tabsContainer) return;
    try {
        var resp = await fetch('/api/stickers/packs', { credentials: 'include', headers: _stickerHeaders(false) });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var data = await resp.json();
        var packs = Array.isArray(data) ? data : (data.own || []).concat(data.favorited || []);
        window._customStickerPacks = packs;
        tabsContainer.innerHTML = packs.map(function(pack) {
            var icon = pack.cover_url
                ? '<img src="' + _sesc(pack.cover_url) + '" class="custom-sticker-tab-icon">'
                : '<span class="custom-sticker-tab-emoji">📦</span>';
            return '<button class="settings-tab custom-sticker-tab" onclick="showCustomPackInPicker(\'' + pack.id + '\',this)" title="' + _sesc(pack.name) + '">' +
                icon + '</button>';
        }).join('');
    } catch(e) {
        tabsContainer.innerHTML = '';
        console.warn('_loadCustomPackTabs error:', e);
    }
};

window.showCustomPackInPicker = async function(packId, btn) {
    document.querySelectorAll('#sticker-modal .settings-tab').forEach(function(t) { t.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    var grid = document.getElementById('sticker-grid');
    if (!grid) return;
    grid.className = '';
    grid.style.cssText = 'max-height:280px;overflow-y:auto;padding:4px;';
    grid.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('common.loading') + '</div>';
    try {
        var resp = await fetch('/api/stickers/packs/' + packId, { credentials: 'include', headers: _stickerHeaders(false) });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        var _rawPack = await resp.json();
        var pack = _rawPack.pack || _rawPack;
        var stickers = pack.stickers || [];
        if (stickers.length === 0) {
            grid.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('stickers.packEmpty') + '</div>';
            return;
        }
        grid.innerHTML = '<div class="custom-sticker-picker-grid">' +
            stickers.map(function(st) {
                return '<div class="custom-sticker-preview" onclick="sendCustomSticker(\'' + _sesc(st.image_url) + '\')" title="' + _sesc(st.emoji || '') + '">' +
                    '<img src="' + _sesc(st.image_url) + '" alt="sticker">' +
                '</div>';
            }).join('') +
        '</div>';
    } catch(e) {
        grid.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('errors.loadFailed') + '</div>';
    }
};

// ── Send custom sticker ──
window.sendCustomSticker = function(imageUrl) {
    if (window.closeModal) window.closeModal('sticker-modal');
    if (window.sendStickerDirect) window.sendStickerDirect('[STICKER] img:' + imageUrl);
};

// openStickerPicker is defined in stickers.js (loaded last)
// Do NOT wrap it here to avoid recursive call loops

// Load packs when stickers tab is selected in settings
var _origSwitchSettingsTab = window.switchSettingsTab;
window.switchSettingsTab = function(tab) {
    _origSwitchSettingsTab(tab);
    if (tab === 'stickers') {
        loadMyPacks();
    }
    if (tab === 'bots') {
        loadMyBots();
    }
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Video Messages (circular video notes)
// ══════════════════════════════════════════════════════════════════════════════

var _videoRecorder = null;
var _videoStream = null;
var _videoChunks = [];

window.startVideoMessage = async function() {
    try {
        _videoStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: 320, height: 320 },
            audio: true
        });

        var overlay = document.createElement('div');
        overlay.id = 'video-record-overlay';
        overlay.innerHTML =
            '<div class="vr-overlay">' +
                '<div class="vr-top">' +
                    '<div class="vr-circle-wrap">' +
                        '<video id="video-preview" autoplay playsinline muted class="vr-preview"></video>' +
                        '<div class="vr-rec-badge"><span class="vr-rec-dot"></span> REC</div>' +
                    '</div>' +
                    '<div class="vr-timer" id="video-timer">0:00</div>' +
                '</div>' +
                '<div class="vr-controls">' +
                    '<button class="vr-btn" onclick="stopVideoMessage(false)">' +
                        '<span class="vr-btn-icon vr-btn-cancel">&#x2715;</span>' +
                        '<span class="vr-btn-label">' + t('common.cancel') + '</span>' +
                    '</button>' +
                    '<button class="vr-btn" onclick="stopVideoMessage(true)">' +
                        '<span class="vr-btn-icon vr-btn-send"><svg width="24" height="24" fill="#fff" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></span>' +
                        '<span class="vr-btn-label">' + t('common.send') + '</span>' +
                    '</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(overlay);

        document.getElementById('video-preview').srcObject = _videoStream;

        _videoChunks = [];
        var mimeType = 'video/webm;codecs=vp8,opus';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'video/webm';
        }
        _videoRecorder = new MediaRecorder(_videoStream, { mimeType: mimeType });
        _videoRecorder.ondataavailable = function(e) {
            if (e.data.size > 0) _videoChunks.push(e.data);
        };
        _videoRecorder.start(100);

        var sec = 0;
        var timerEl = document.getElementById('video-timer');
        var tid = setInterval(function() {
            sec++;
            if (timerEl) timerEl.textContent = Math.floor(sec / 60) + ':' + (sec % 60).toString().padStart(2, '0');
            if (sec >= 60) window.stopVideoMessage(true);
        }, 1000);
        overlay._tid = tid;

    } catch(e) {
        alert((window.t?.('errors.noCameraAccess')||'No camera access')+': '+e.message);
    }
};

window.stopVideoMessage = async function(send) {
    var overlay = document.getElementById('video-record-overlay');
    if (overlay && overlay._tid) clearInterval(overlay._tid);

    if (_videoRecorder && _videoRecorder.state !== 'inactive') {
        _videoRecorder.stop();
    }
    if (_videoStream) {
        _videoStream.getTracks().forEach(function(t) { t.stop(); });
    }

    if (send && _videoChunks.length > 0) {
        await new Promise(function(r) { setTimeout(r, 300); });
        var blob = new Blob(_videoChunks, { type: 'video/webm' });
        var file = new File([blob], 'video_' + Date.now() + '.webm', { type: 'video/webm' });

        var S = window.AppState;
        if (S && S.currentRoom) {
            var formData = new FormData();
            formData.append('file', file);
            try {
                var headers = {};
                if (S.csrfToken) headers['X-CSRF-Token'] = S.csrfToken;
                await fetch('/api/files/upload/' + S.currentRoom.id, {
                    method: 'POST',
                    body: formData,
                    credentials: 'include',
                    headers: headers,
                });
            } catch(e) { console.warn('Video upload failed:', e); }
        }
    }

    if (overlay) overlay.remove();
    _videoRecorder = null;
    _videoStream = null;
    _videoChunks = [];
};

// ══════════════════════════════════════════════════════════════════════════════
// FEATURE: Statuses (24-hour ephemeral posts)
// ══════════════════════════════════════════════════════════════════════════════

window.openStatusModal = function() {
    var ta = document.getElementById('status-text');
    if (ta) ta.value = '';
    if (window.openModal) window.openModal('status-modal');
};

window.postStatus = async function() {
    var text = (document.getElementById('status-text')?.value || '').trim();
    if (!text) return;
    try {
        await window.api('POST', '/api/statuses', { text: text });
        if (window.closeModal) window.closeModal('status-modal');
        window.loadStatuses();
    } catch(e) { alert(e.message); }
};

window.loadStatuses = async function() {
    try {
        var data = await window.api('GET', '/api/statuses');
        var el = document.getElementById('status-list');
        if (!el) return;
        if (!data.users || !data.users.length) { el.innerHTML = ''; return; }

        el.innerHTML = data.users.map(function(u) {
            var avatar;
            if (u.avatar_url) {
                avatar = '<img src="' + u.avatar_url + '" style="width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid var(--accent);">';
            } else {
                avatar = '<div style="width:36px;height:36px;border-radius:50%;border:2px solid var(--accent);display:flex;align-items:center;justify-content:center;font-size:18px;background:var(--bg3);">' + (u.avatar_emoji || '\u{1F464}') + '</div>';
            }
            var latest = u.statuses[0];
            var previewText = latest && latest.text ? latest.text : '';
            if (previewText.length > 40) previewText = previewText.substring(0, 40) + '...';
            return '<div style="display:flex;align-items:center;gap:8px;padding:6px 4px;cursor:pointer;border-radius:8px;transition:background 0.1s;" ' +
                'onmouseover="this.style.background=\'var(--bg3)\'" onmouseout="this.style.background=\'\'" ' +
                'onclick="viewStatus(' + u.user_id + ')">' +
                avatar +
                '<div style="flex:1;min-width:0;">' +
                    '<div style="font-weight:700;font-size:12px;">' + (u.display_name || u.username) + '</div>' +
                    '<div style="font-size:11px;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + previewText + '</div>' +
                '</div>' +
            '</div>';
        }).join('');
    } catch(e) { console.warn('loadStatuses error:', e); }
};

window._statusData = null;

window.viewStatus = async function(userId) {
    try {
        var data = await window.api('GET', '/api/statuses');
        var userEntry = (data.users || []).find(function(u) { return u.user_id === userId; });
        if (!userEntry || !userEntry.statuses.length) {
            alert(window.t?.('statuses.noneActive')||'No active statuses');
            return;
        }
        var title = document.getElementById('status-viewer-title');
        if (title) title.textContent = t('statuses.statusesOf', {name: userEntry.display_name || userEntry.username});
        var list = document.getElementById('status-viewer-list');
        if (list) {
            list.innerHTML = userEntry.statuses.map(function(s) {
                var createdAt = s.created_at ? new Date(s.created_at).toLocaleString('ru') : '';
                return '<div style="padding:12px;margin-bottom:8px;background:var(--bg3);border-radius:var(--radius);border-left:3px solid var(--accent);">' +
                    '<div style="font-size:14px;margin-bottom:4px;">' + (s.text || '') + '</div>' +
                    '<div style="font-size:10px;color:var(--text3);font-family:var(--mono);">' + createdAt + '</div>' +
                '</div>';
            }).join('');
        }
        if (window.openModal) window.openModal('status-viewer-modal');
    } catch(e) { alert(e.message); }
};

// ── Media Gallery ──
window._galleryFiles = [];
window._galleryTab = 'photo';

window.openGallery = async function() {
    var S = window.AppState;
    if (!S || !S.currentRoom) return;
    if (window.openModal) window.openModal('gallery-modal');
    var grid = document.getElementById('gallery-grid');
    grid.innerHTML = '<div class="gallery-empty">' + t('common.loading') + '</div>';
    // Reset tab to photo
    window._galleryTab = 'photo';
    document.querySelectorAll('.gallery-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.galleryTab === 'photo');
    });
    try {
        var data = await window.api('GET', '/api/files/room/' + S.currentRoom.id);
        window._galleryFiles = data.files || [];
        renderGallery();
    } catch(e) {
        grid.innerHTML = '<div class="gallery-empty">' + t('errors.loadFailed') + '</div>';
    }
};

window.switchGalleryTab = function(tab) {
    window._galleryTab = tab;
    document.querySelectorAll('.gallery-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.galleryTab === tab);
    });
    renderGallery();
};

function renderGallery() {
    var grid = document.getElementById('gallery-grid');
    var tab = window._galleryTab;
    var files = window._galleryFiles;
    var filtered;

    if (tab === 'photo') {
        filtered = files.filter(function(f) { return f.mime_type && f.mime_type.startsWith('image/'); });
    } else if (tab === 'video') {
        filtered = files.filter(function(f) { return f.mime_type && f.mime_type.startsWith('video/'); });
    } else {
        filtered = files.filter(function(f) {
            return !f.mime_type || (!f.mime_type.startsWith('image/') && !f.mime_type.startsWith('video/'));
        });
    }

    if (!filtered.length) {
        var labels = { photo: t('gallery.noPhotos'), video: t('gallery.noVideos'), files: t('gallery.noFiles') };
        grid.innerHTML = '<div class="gallery-empty">' + (labels[tab] || (window.t?.('ui.empty')||'Empty')) + '</div>';
        return;
    }

    if (tab === 'photo') {
        grid.className = 'gallery-grid gallery-grid-media';
        grid.innerHTML = filtered.map(function(f) {
            var safeName = (f.file_name || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
            return '<div class="gallery-thumb" onclick="closeModal(\'gallery-modal\');window.openImageViewer(\'' + f.download_url + '\',\'' + safeName + '\')">' +
                '<img src="' + f.download_url + '" alt="' + safeName + '" loading="lazy">' +
            '</div>';
        }).join('');
    } else if (tab === 'video') {
        grid.className = 'gallery-grid gallery-grid-media';
        grid.innerHTML = filtered.map(function(f) {
            var safeName = (f.file_name || '').replace(/"/g, '&quot;');
            return '<div class="gallery-thumb gallery-thumb-video" onclick="openGalleryVideo(\'' + f.download_url + '\',\'' + safeName + '\')">' +
                '<video src="' + f.download_url + '" preload="metadata" muted></video>' +
                '<div class="gallery-play-icon"><svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="white" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>' +
            '</div>';
        }).join('');
    } else {
        grid.className = 'gallery-grid gallery-grid-files';
        grid.innerHTML = filtered.map(function(f) {
            var size = f.size_bytes;
            var sizeStr;
            if (size < 1024) sizeStr = size + ' ' + t('files.bytes');
            else if (size < 1024 * 1024) sizeStr = (size / 1024).toFixed(1) + ' ' + t('files.kb');
            else sizeStr = (size / 1024 / 1024).toFixed(1) + ' ' + t('files.mb');
            var safeName = (f.file_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return '<a href="' + f.download_url + '" download class="gallery-file-item">' +
                '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>' +
                '<div class="gallery-file-info">' +
                    '<div class="gallery-file-name">' + safeName + '</div>' +
                    '<div class="gallery-file-meta">' + sizeStr + (f.uploader ? ' \u00B7 ' + f.uploader : '') + '</div>' +
                '</div>' +
            '</a>';
        }).join('');
    }
}

window.openGalleryVideo = function(url, name) {
    // Close gallery and open a fullscreen video player using the image viewer overlay approach
    closeModal('gallery-modal');
    var overlay = document.getElementById('image-viewer-overlay');
    var img = document.getElementById('image-viewer-img');
    var nameEl = document.getElementById('image-viewer-name');
    // Replace img with video temporarily
    var video = document.createElement('video');
    video.src = url;
    video.controls = true;
    video.autoplay = true;
    video.style.cssText = 'max-width:90vw;max-height:80vh;border-radius:8px;outline:none;';
    video.id = 'gallery-video-player';
    img.style.display = 'none';
    img.parentNode.insertBefore(video, img.nextSibling);
    nameEl.textContent = name;
    overlay.classList.add('show');

    // Clean up when overlay closes
    var obs = new MutationObserver(function(mutations) {
        mutations.forEach(function(m) {
            if (!overlay.classList.contains('show')) {
                var vp = document.getElementById('gallery-video-player');
                if (vp) { vp.pause(); vp.remove(); }
                img.style.display = '';
                obs.disconnect();
            }
        });
    });
    obs.observe(overlay, { attributes: true, attributeFilter: ['class'] });
};

// ══════════════════════════════════════════════════════════════════════════════
// Bot Management UI
// ══════════════════════════════════════════════════════════════════════════════

window.showCreateBotForm = function() {
    var form = document.getElementById('create-bot-form');
    if (form) form.style.display = '';
};

window.hideCreateBotForm = function() {
    var form = document.getElementById('create-bot-form');
    if (form) form.style.display = 'none';
    var nameInput = document.getElementById('bot-name');
    var descInput = document.getElementById('bot-description');
    if (nameInput) nameInput.value = '';
    if (descInput) descInput.value = '';
};

window.createBot = async function() {
    var name = document.getElementById('bot-name')?.value?.trim();
    var description = document.getElementById('bot-description')?.value?.trim() || '';
    if (!name || name.length < 2) {
        window.vxAlert(t('bots.nameMinLength'));
        return;
    }
    try {
        var resp = await window.api('POST', '/api/bots', { name: name, description: description });
        if (resp.ok) {
            window.hideCreateBotForm();
            window.loadMyBots();
            await window.vxAlert(t('bots.botCreated'), { token: resp.api_token });
        }
    } catch (e) {
        window.vxAlert(t('errors.errorWithMessage', {message: e.message || e}));
    }
};

window.loadMyBots = async function() {
    var container = document.getElementById('bots-list');
    if (!container) return;
    try {
        var resp = await window.api('GET', '/api/bots');
        var bots = resp.bots || [];
        if (bots.length === 0) {
            container.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:12px;padding:24px 0;">' + t('bots.noBotsYet') + '</div>';
            return;
        }
        container.innerHTML = bots.map(function(b) {
            var cmds = (b.commands || []).map(function(c) {
                return '<code>' + _escBot(c.command) + '</code> — ' + _escBot(c.description || '');
            }).join('<br>');
            // Mini App row: shows current URL and edit/test controls
            var miniAppHtml = '';
            miniAppHtml += '<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);">' +
                '<div style="font-size:11px;color:var(--text3);margin-bottom:4px;">Mini App URL:</div>' +
                '<div class="miniapp-url-row">' +
                    '<input class="form-input" id="miniapp-url-' + b.bot_id + '" type="url" ' +
                        'placeholder="https://example.com/app" value="' + _escBot(b.mini_app_url || '') + '" ' +
                        'style="font-size:12px;padding:4px 8px;" maxlength="500">' +
                    '<button class="btn btn-primary miniapp-test-btn" onclick="saveBotMiniAppUrl(' + b.bot_id + ')" ' +
                        'title="Save mini app URL">Save</button>' +
                    (b.mini_app_url && b.mini_app_enabled ?
                        '<button class="btn btn-secondary miniapp-test-btn" onclick="testBotMiniApp(' + b.bot_id + ', \'' + _escBot(b.mini_app_url || '') + '\', \'' + _escBot(b.name) + '\')" ' +
                            'title="Test mini app">Test</button>' : '') +
                '</div>' +
                (b.mini_app_enabled ? '<div style="font-size:10px;color:var(--green);margin-top:4px;">Mini App active</div>' :
                    '<div style="font-size:10px;color:var(--text3);margin-top:4px;">No mini app configured</div>') +
            '</div>';
            return '<div class="bot-card" style="background:var(--bg3);border-radius:8px;padding:12px;">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                    '<div>' +
                        '<div style="font-weight:700;font-size:14px;">' +
                            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>' + _escBot(b.name) +
                            (b.is_active ? '' : ' <span style="color:var(--danger);font-size:11px;">(disabled)</span>') +
                        '</div>' +
                        '<div style="font-size:11px;color:var(--text3);font-family:var(--mono);">@' + _escBot(b.username) + '</div>' +
                        (b.description ? '<div style="font-size:12px;color:var(--text2);margin-top:4px;">' + _escBot(b.description) + '</div>' : '') +
                    '</div>' +
                    '<div style="display:flex;gap:4px;">' +
                        '<button class="btn btn-secondary" onclick="regenerateBotToken(' + b.bot_id + ')" style="font-size:11px;padding:2px 8px;" title="' + t('bots.getToken') + '"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg> Token</button>' +
                        '<button class="btn btn-secondary" onclick="editBotCommands(' + b.bot_id + ')" style="font-size:11px;padding:2px 8px;">Commands</button>' +
                        '<button class="btn btn-secondary" onclick="regenerateBotToken(' + b.bot_id + ')" style="font-size:11px;padding:2px 8px;" title="' + t('bots.regenerate') + '"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg></button>' +
                        '<button class="btn btn-secondary" style="font-size:11px;padding:2px 8px;color:var(--danger);" onclick="deleteBot(' + b.bot_id + ')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>' +
                    '</div>' +
                '</div>' +
                (cmds ? '<div style="margin-top:8px;font-size:12px;color:var(--text2);">' + cmds + '</div>' : '') +
                miniAppHtml +
                '<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;">' +
                    '<div style="display:flex;align-items:center;gap:8px;">' +
                        '<label style="font-size:11px;display:flex;align-items:center;gap:4px;cursor:pointer;">' +
                            '<input type="checkbox" ' + (b.is_public ? 'checked' : '') + ' onchange="toggleBotPublish(' + b.bot_id + ',this.checked,document.getElementById(\'bot-cat-' + b.bot_id + '\').value)" style="width:14px;height:14px;accent-color:var(--accent);">' +
                            ' ' + t('bots.marketplace') + '' +
                        '</label>' +
                        '<select id="bot-cat-' + b.bot_id + '" style="font-size:11px;padding:2px 6px;background:var(--bg2);border:1px solid var(--border);border-radius:4px;color:var(--text);" onchange="toggleBotPublish(' + b.bot_id + ',true,this.value)">' +
                            '<option value="utilities"' + (b.category==='utilities'?' selected':'') + '>' + t('bots.catUtilities') + '</option>' +
                            '<option value="games"' + (b.category==='games'?' selected':'') + '>' + t('bots.catGames') + '</option>' +
                            '<option value="moderation"' + (b.category==='moderation'?' selected':'') + '>' + t('bots.catModeration') + '</option>' +
                            '<option value="music"' + (b.category==='music'?' selected':'') + '>' + t('bots.catMusic') + '</option>' +
                            '<option value="productivity"' + (b.category==='productivity'?' selected':'') + '>' + t('bots.catProductivity') + '</option>' +
                            '<option value="social"' + (b.category==='social'?' selected':'') + '>' + t('bots.catSocial') + '</option>' +
                            '<option value="fun"' + (b.category==='fun'?' selected':'') + '>' + t('bots.catFun') + '</option>' +
                            '<option value="other"' + (b.category==='other'?' selected':'') + '>' + t('bots.catOther') + '</option>' +
                        '</select>' +
                    '</div>' +
                    (b.is_public ? '<div style="font-size:10px;color:var(--text3);">' +
                        t('bots.installsCount', {count: _escBot(String(b.installs || 0))}) + ', ' +
                        _escBot(String(b.rating || 0)) + ' (' + t('bots.ratingsCount', {count: _escBot(String(b.rating_count || 0))}) + ')' +
                    '</div>' : '') +
                '</div>' +
            '</div>';
        }).join('');
    } catch (e) {
        container.innerHTML = '<div style="text-align:center;color:var(--danger);font-size:12px;padding:24px 0;">' + t('errors.loadError', {message: e.message || e}) + '</div>';
    }
};

function _escBot(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

window.copyBotToken = async function(botId) {
    try {
        var resp = await window.api('GET', '/api/bots/' + botId + '/token');
        if (resp.api_token) {
            await window.vxAlert('API Token', { token: resp.api_token });
        }
    } catch (e) {
        window.vxAlert(t('errors.errorWithMessage', {message: e.message || e}));
    }
};

window.regenerateBotToken = async function(botId) {
    if (!await window.vxConfirm(t('bots.regenerateTokenConfirm'), { danger: true })) return;
    try {
        var resp = await window.api('POST', '/api/bots/' + botId + '/regenerate-token');
        if (resp.ok) {
            await window.vxAlert(t('bots.newToken'), { token: resp.api_token });
            window.loadMyBots();
        }
    } catch (e) {
        window.vxAlert(t('errors.errorWithMessage', {message: e.message || e}));
    }
};

window.deleteBot = async function(botId) {
    if (!await window.vxConfirm(t('bots.deleteBotConfirm'), { danger: true })) return;
    try {
        var resp = await window.api('DELETE', '/api/bots/' + botId);
        if (resp.ok) {
            window.loadMyBots();
        }
    } catch (e) {
        window.vxAlert(t('errors.errorWithMessage', {message: e.message || e}));
    }
};

window.showAddBotToRoom = async function() {
    var list = document.getElementById('add-bot-to-room-list');
    if (!list) return;
    if (list.style.display !== 'none') {
        list.style.display = 'none';
        return;
    }
    list.style.display = '';
    list.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:11px;padding:8px;">' + t('common.loading') + '</div>';
    try {
        var resp = await window.api('GET', '/api/bots');
        var bots = resp.bots || [];
        if (bots.length === 0) {
            list.innerHTML = '<div style="text-align:center;color:var(--text3);font-size:11px;padding:8px;">' + t('bots.noBotsCreateHint') + '</div>';
            return;
        }
        var S = window.AppState;
        var roomId = S.currentRoom?.id;
        list.innerHTML = bots.map(function(b) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:var(--bg3);border-radius:6px;margin-bottom:4px;">' +
                '<span style="font-size:12px;"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:3px;"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>' + _escBot(b.name) + '</span>' +
                '<button class="btn btn-primary" style="font-size:11px;padding:2px 8px;" onclick="addBotToCurrentRoom(' + b.bot_id + ')">' + t('common.add') + '</button>' +
            '</div>';
        }).join('');
    } catch (e) {
        list.innerHTML = '<div style="color:var(--danger);font-size:11px;padding:8px;">' + (e.message || e) + '</div>';
    }
};

window.addBotToCurrentRoom = async function(botId) {
    var S = window.AppState;
    var roomId = S.currentRoom?.id;
    if (!roomId) return;
    try {
        await window.api('POST', '/api/bots/' + botId + '/rooms/' + roomId);
        alert(window.t?.('notifications.botAddedToRoom')||'Bot added to room');
        document.getElementById('add-bot-to-room-list').style.display = 'none';
    } catch (e) {
        alert((window.t?.('errors.generic')||'Error')+': '+(e.message||e));
    }
};

window.editBotCommands = async function(botId) {
    var cmdsJson = await window.vxPrompt(
        t('bots.enterCommandsJson'),
        '', '[]'
    );
    if (cmdsJson === null) return;
    if (cmdsJson.trim() === '') cmdsJson = '[]';
    try {
        JSON.parse(cmdsJson);
    } catch {
        window.vxAlert(t('bots.invalidJsonFormat'));
        return;
    }
    window.api('PUT', '/api/bots/' + botId, { commands: cmdsJson })
        .then(function() { window.loadMyBots(); })
        .catch(function(e) { window.vxAlert(t('errors.errorWithMessage', {message: e.message || e})); });
};

// ══════════════════════════════════════════════════════════════════════════════
// Mini App — Save URL for a bot
// ══════════════════════════════════════════════════════════════════════════════

window.saveBotMiniAppUrl = async function(botId) {
    var input = document.getElementById('miniapp-url-' + botId);
    if (!input) return;
    var url = input.value.trim();
    try {
        await window.api('PUT', '/api/bots/' + botId, { mini_app_url: url });
        window.loadMyBots();
    } catch (e) {
        alert((window.t?.('errors.generic')||'Error')+': '+(e.message||e));
    }
};

window.testBotMiniApp = function(botId, url, title) {
    window.openMiniApp(botId, url, title || 'Mini App');
};

// ══════════════════════════════════════════════════════════════════════════════
// Mini App Bridge — postMessage communication between Vortex and mini app iframe
//
// PROTOCOL (for bot/mini-app developers):
//
// 1. When a mini app is opened, the iframe URL receives query parameters:
//    ?user_id=<id>&username=<username>&display_name=<name>&theme=<dark|light>&bot_id=<id>
//
// 2. The parent (Vortex) sends an init event via postMessage after iframe loads:
//    { type: "vortex_init", user_id, username, display_name, theme, accent_color, bot_id }
//
// 3. The mini app can send messages to Vortex via window.parent.postMessage():
//    { type: "close" }                              — close the mini app
//    { type: "send_message", room_id, text }        — send a message to a room
//    { type: "get_user" }                           — request current user info
//    { type: "set_title", title }                   — change the header title
//    { type: "expand" }                             — toggle fullscreen
//    { type: "haptic", style }                      — trigger haptic feedback (vibrate)
//    { type: "ready" }                              — mini app finished loading
//
// 4. Vortex responds to get_user with:
//    { type: "user_info", user_id, username, display_name, theme }
//
// ══════════════════════════════════════════════════════════════════════════════

(function() {
    var _miniAppState = {
        botId: null,
        url: null,
        title: null,
        expanded: false,
    };

    window.openMiniApp = function(botId, url, title) {
        if (!url) {
            alert(window.t?.('errors.noMiniAppUrl')||'No Mini App URL configured');
            return;
        }

        var panel = document.getElementById('miniapp-panel');
        var frame = document.getElementById('miniapp-frame');
        var titleEl = document.getElementById('miniapp-title');
        var loading = document.getElementById('miniapp-loading');

        if (!panel || !frame) return;

        _miniAppState.botId = botId;
        _miniAppState.url = url;
        _miniAppState.title = title || 'Mini App';
        _miniAppState.expanded = false;

        titleEl.textContent = _miniAppState.title;

        panel.classList.add('show');
        loading.style.display = '';
        frame.style.display = 'none';

        var S = window.AppState;
        var user = S ? S.user : null;
        var theme = document.body.getAttribute('data-theme') || 'dark';
        var separator = url.includes('?') ? '&' : '?';
        var iframeUrl = url + separator +
            'user_id=' + encodeURIComponent(user ? user.id : '') +
            '&username=' + encodeURIComponent(user ? user.username : '') +
            '&display_name=' + encodeURIComponent(user ? (user.display_name || user.username) : '') +
            '&theme=' + encodeURIComponent(theme) +
            '&bot_id=' + encodeURIComponent(botId);

        frame.src = iframeUrl;

        frame.onload = function() {
            loading.style.display = 'none';
            frame.style.display = '';
            try {
                frame.contentWindow.postMessage({
                    type: 'vortex_init',
                    user_id: user ? user.id : null,
                    username: user ? user.username : null,
                    display_name: user ? (user.display_name || user.username) : null,
                    theme: theme,
                    accent_color: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),
                    bot_id: botId,
                }, '*');
            } catch (e) {
                console.warn('Mini App: could not send init message:', e);
            }
        };

        setTimeout(function() {
            if (loading.style.display !== 'none') {
                loading.innerHTML = '<div style="color:var(--red);font-size:13px;">Failed to load Mini App</div>' +
                    '<button class="btn btn-secondary" onclick="closeMiniApp()" style="margin-top:8px;">Close</button>';
            }
        }, 15000);
    };

    window.closeMiniApp = function() {
        var panel = document.getElementById('miniapp-panel');
        var frame = document.getElementById('miniapp-frame');
        var loading = document.getElementById('miniapp-loading');

        if (panel) panel.classList.remove('show');
        if (frame) {
            frame.src = 'about:blank';
            frame.style.display = 'none';
        }
        if (loading) {
            loading.style.display = 'none';
            loading.innerHTML = '<div class="spinner"></div><span>Loading Mini App...</span>';
        }

        _miniAppState.botId = null;
        _miniAppState.url = null;
        _miniAppState.title = null;
        _miniAppState.expanded = false;
    };

    window.toggleMiniAppExpand = function() {
        var header = document.querySelector('.miniapp-header');
        if (!header) return;
        _miniAppState.expanded = !_miniAppState.expanded;
        header.style.display = _miniAppState.expanded ? 'none' : '';
    };

    window.addEventListener('message', function(event) {
        var frame = document.getElementById('miniapp-frame');
        if (!frame || !frame.contentWindow) return;
        if (event.source !== frame.contentWindow) return;

        var data = event.data;
        if (!data || typeof data !== 'object' || !data.type) return;

        switch (data.type) {
            case 'close':
                window.closeMiniApp();
                break;

            case 'send_message':
                if (data.room_id && data.text) {
                    window.api('POST', '/api/bot/send', {
                        room_id: data.room_id,
                        text: data.text,
                    }).catch(function(e) {
                        console.warn('Mini App send_message failed:', e);
                    });
                }
                break;

            case 'get_user':
                var S = window.AppState;
                var user = S ? S.user : null;
                try {
                    frame.contentWindow.postMessage({
                        type: 'user_info',
                        user_id: user ? user.id : null,
                        username: user ? user.username : null,
                        display_name: user ? (user.display_name || user.username) : null,
                        theme: document.body.getAttribute('data-theme') || 'dark',
                    }, '*');
                } catch (e) {
                    console.warn('Mini App: could not reply to get_user:', e);
                }
                break;

            case 'set_title':
                if (data.title) {
                    var titleEl = document.getElementById('miniapp-title');
                    if (titleEl) titleEl.textContent = data.title;
                }
                break;

            case 'expand':
                window.toggleMiniAppExpand();
                break;

            case 'haptic':
                if (navigator.vibrate) {
                    var patterns = {
                        light: [10],
                        medium: [30],
                        heavy: [50],
                        success: [10, 50, 10],
                        warning: [30, 30, 30],
                        error: [50, 50, 50],
                    };
                    navigator.vibrate(patterns[data.style] || [10]);
                }
                break;

            case 'ready':
                var loadingEl = document.getElementById('miniapp-loading');
                if (loadingEl) loadingEl.style.display = 'none';
                if (frame) frame.style.display = '';
                break;

            default:
                console.warn('Mini App: unknown message type:', data.type);
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var panel = document.getElementById('miniapp-panel');
            if (panel && panel.classList.contains('show')) {
                window.closeMiniApp();
                e.preventDefault();
                e.stopPropagation();
            }
        }
    });
})();

// ══════════════════════════════════════════════════════════════════════════════
// Bot Marketplace: publish toggle from bot settings
// ══════════════════════════════════════════════════════════════════════════════

window.toggleBotPublish = async function(botId, isPublic, category) {
    try {
        await window.api('POST', '/api/bots/' + botId + '/publish', {
            is_public: isPublic,
            category: category || 'other'
        });
        window.loadMyBots();
    } catch (e) {
        alert((window.t?.('errors.generic')||'Error')+': '+(e.message||e));
    }
};

// ══════════════════════════════════════════════════════════════════════════════
// Bot Marketplace UI
// ══════════════════════════════════════════════════════════════════════════════

var _mpState = {
    category: '',
    sort: 'rating',
    searchTimeout: null,
    userRooms: []
};

var _mpCatLabels = {
    utilities: t('bots.catUtilities'),
    games: t('bots.catGames'),
    moderation: t('bots.catModeration'),
    music: t('bots.catMusic'),
    productivity: t('bots.catProductivity'),
    social: t('bots.catSocial'),
    fun: t('bots.catFun'),
    other: t('bots.catOther')
};

window.openMarketplace = function() {
    openModal('marketplace-modal');
    document.getElementById('mp-list-view').style.display = 'flex';
    document.getElementById('mp-detail-view').style.display = 'none';
    var searchInput = document.getElementById('mp-search');
    if (searchInput) searchInput.value = '';
    _mpState.category = '';
    _mpState.sort = 'rating';
    document.querySelectorAll('.marketplace-sort-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.sort === 'rating');
    });
    mpLoadCategories();
    mpLoadBots();
    mpLoadUserRooms();
};

window.mpLoadCategories = async function() {
    var container = document.getElementById('mp-categories');
    if (!container) return;
    try {
        var data = await window.api('GET', '/api/marketplace/categories');
        var cats = data.categories || [];
        var html = '<button class="marketplace-cat-pill active" onclick="mpSetCategory(\'\',this)">' + t('common.all') + '<span class="cat-count">' + (data.total || 0) + '</span></button>';
        cats.forEach(function(c) {
            html += '<button class="marketplace-cat-pill" onclick="mpSetCategory(\'' + c.id + '\',this)">' +
                (_mpCatLabels[c.id] || c.id) +
                '<span class="cat-count">' + c.count + '</span></button>';
        });
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '';
    }
};

window.mpSetCategory = function(cat, btn) {
    _mpState.category = cat;
    document.querySelectorAll('.marketplace-cat-pill').forEach(function(p) { p.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    mpLoadBots();
};

window.mpSetSort = function(sort, btn) {
    _mpState.sort = sort;
    document.querySelectorAll('.marketplace-sort-btn').forEach(function(b) { b.classList.remove('active'); });
    if (btn) btn.classList.add('active');
    mpLoadBots();
};

window.mpSearch = function(q) {
    clearTimeout(_mpState.searchTimeout);
    _mpState.searchTimeout = setTimeout(function() {
        if (q.trim()) {
            mpSearchBots(q.trim());
        } else {
            mpLoadBots();
        }
    }, 300);
};

window.mpSearchBots = async function(q) {
    var grid = document.getElementById('mp-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="marketplace-loading">' + t('search.searching') + '</div>';
    try {
        var data = await window.api('GET', '/api/marketplace/search?q=' + encodeURIComponent(q));
        mpRenderGrid(data.bots || []);
    } catch (e) {
        grid.innerHTML = '<div class="marketplace-empty">' + t('search.searchFailed') + '</div>';
    }
};

window.mpLoadBots = async function() {
    var grid = document.getElementById('mp-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="marketplace-loading">' + t('common.loading') + '</div>';
    try {
        var url = '/api/marketplace?sort=' + _mpState.sort + '&limit=50';
        if (_mpState.category) url += '&category=' + _mpState.category;
        var data = await window.api('GET', url);
        mpRenderGrid(data.bots || []);
    } catch (e) {
        grid.innerHTML = '<div class="marketplace-empty">' + t('errors.loadFailed') + '</div>';
    }
};

function mpRenderGrid(bots) {
    var grid = document.getElementById('mp-grid');
    if (!grid) return;
    if (bots.length === 0) {
        grid.innerHTML = '<div class="marketplace-empty" style="grid-column:1/-1;">' + t('bots.noBotsInMarketplace') + '</div>';
        return;
    }
    grid.innerHTML = bots.map(function(b) {
        var avatarHtml = b.avatar_url ?
            '<img src="' + _escBot(b.avatar_url) + '" alt="">' :
            '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>';
        return '<div class="marketplace-card" onclick="mpOpenDetail(' + b.bot_id + ')">' +
            '<div class="marketplace-card-top">' +
                '<div class="marketplace-card-avatar">' + avatarHtml + '</div>' +
                '<div class="marketplace-card-info">' +
                    '<div class="marketplace-card-name">' + _escBot(b.name) + '</div>' +
                    '<div class="marketplace-card-desc">' + _escBot(b.description) + '</div>' +
                '</div>' +
            '</div>' +
            '<div class="marketplace-card-bottom">' +
                '<div class="marketplace-card-cat">' + (_mpCatLabels[b.category] || b.category) + '</div>' +
                '<div class="marketplace-card-stats">' +
                    '<span class="stat-icon">' + mpStarsHtml(b.rating, true) + '</span>' +
                    '<span class="stat-icon"><svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> ' + (b.installs || 0) + '</span>' +
                '</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

function mpStarsHtml(rating, small) {
    var html = '<span class="marketplace-stars">';
    var full = Math.floor(rating);
    var half = (rating - full) >= 0.3;
    var sz = small ? '12' : '14';
    for (var i = 1; i <= 5; i++) {
        if (i <= full) {
            html += '<svg width="' + sz + '" height="' + sz + '" class="star-filled" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>';
        } else if (i === full + 1 && half) {
            html += '<svg width="' + sz + '" height="' + sz + '" class="star-half" viewBox="0 0 24 24" fill="currentColor"><path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4V6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"/></svg>';
        } else {
            html += '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 24 24" fill="currentColor"><path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z"/></svg>';
        }
    }
    html += '</span>';
    return html;
}

window.mpLoadUserRooms = async function() {
    try {
        var data = await window.api('GET', '/api/rooms/my');
        _mpState.userRooms = (data.rooms || []).filter(function(r) { return r.type !== 'dm'; });
    } catch (e) {
        _mpState.userRooms = [];
    }
};

window.mpOpenDetail = async function(botId) {
    document.getElementById('mp-list-view').style.display = 'none';
    document.getElementById('mp-detail-view').style.display = 'flex';
    var content = document.getElementById('mp-detail-content');
    if (!content) return;
    content.innerHTML = '<div class="marketplace-loading">' + t('common.loading') + '</div>';

    try {
        var bot = await window.api('GET', '/api/marketplace/' + botId);
        var reviews = await window.api('GET', '/api/marketplace/' + botId + '/reviews');

        var avatarHtml = bot.avatar_url ?
            '<img src="' + _escBot(bot.avatar_url) + '" alt="">' :
            '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="currentColor" viewBox="0 0 24 24"><path d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7 13H6v-2h1v2zm5 4c-1.1 0-2-.9-2-2h4c0 1.1-.9 2-2 2zm4-4h-1v-2h1v2zm-6-2v-2h4v2h-4z"/></svg>';

        var cmdsHtml = '';
        var cmds = bot.commands || [];
        if (cmds.length > 0) {
            cmdsHtml = '<div class="marketplace-detail-commands"><h4>' + t('bots.commands') + '</h4>';
            cmds.forEach(function(c) {
                cmdsHtml += '<div class="marketplace-detail-cmd"><code>' + _escBot(c.command) + '</code><span>' + _escBot(c.description || '') + '</span></div>';
            });
            cmdsHtml += '</div>';
        }

        // Room selector
        var roomOptions = _mpState.userRooms.map(function(r) {
            return '<option value="' + r.id + '">' + _escBot(r.name) + '</option>';
        }).join('');
        var installHtml = roomOptions ?
            '<div class="marketplace-room-select">' +
                '<label>' + t('bots.addToRoom') + '</label>' +
                '<div style="display:flex;gap:8px;">' +
                    '<select id="mp-install-room" style="flex:1;padding:8px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;">' + roomOptions + '</select>' +
                    '<button class="btn btn-primary" onclick="mpInstallBot(' + botId + ')" style="white-space:nowrap;font-size:12px;">' + t('bots.install') + '</button>' +
                '</div>' +
            '</div>' :
            '<div style="font-size:12px;color:var(--text3);margin-bottom:16px;">' + t('bots.noRoomsAvailable') + '</div>';

        // Mini app button
        var miniAppHtml = '';
        if (bot.mini_app_url) {
            miniAppHtml = '<div style="margin-bottom:16px;">' +
                '<button class="btn btn-secondary" onclick="window.open(\'' + _escBot(bot.mini_app_url) + '\',\'_blank\')" style="font-size:12px;">' +
                    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:4px;"><path d="M19 19H5V5h7V3H5a2 2 0 00-2 2v14a2 2 0 002 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>' +
                    t('bots.openApp') + '</button>' +
            '</div>';
        }

        // Reviews
        var reviewsHtml = '<div class="marketplace-reviews"><h4>' + t('bots.reviews', {count: bot.rating_count || 0}) + '</h4>';

        // Review form
        var existingRating = (bot.user_review && bot.user_review.rating) || 0;
        var existingText = (bot.user_review && bot.user_review.text) || '';
        reviewsHtml += '<div class="marketplace-review-form">' +
            '<label>' + (existingRating ? t('bots.yourReviewUpdate') : t('bots.leaveReview')) + '</label>' +
            '<div class="marketplace-star-input" id="mp-star-input" data-bot="' + botId + '">';
        for (var i = 1; i <= 5; i++) {
            reviewsHtml += '<span class="star' + (i <= existingRating ? ' active' : '') + '" data-val="' + i + '" onclick="mpSelectStar(this,' + i + ')">&#9733;</span>';
        }
        reviewsHtml += '</div>' +
            '<textarea id="mp-review-text" placeholder="' + t('bots.commentOptional') + '" maxlength="500">' + _escBot(existingText) + '</textarea>' +
            '<button class="btn btn-primary" onclick="mpSubmitReview(' + botId + ')" style="font-size:12px;margin-top:8px;">' + t('common.send') + '</button>' +
        '</div>';

        // Existing reviews list
        var revList = reviews.reviews || [];
        if (revList.length > 0) {
            revList.forEach(function(r) {
                var rAvatar = r.avatar_url ?
                    '<img src="' + _escBot(r.avatar_url) + '" alt="">' :
                    '<span>' + (r.avatar_emoji || '&#x1F464;') + '</span>';
                var rDate = r.created_at ? new Date(r.created_at).toLocaleDateString('ru') : '';
                reviewsHtml += '<div class="marketplace-review-item">' +
                    '<div class="marketplace-review-avatar">' + rAvatar + '</div>' +
                    '<div class="marketplace-review-body">' +
                        '<div class="marketplace-review-top">' +
                            '<span class="marketplace-review-name">' + _escBot(r.display_name || r.username) + '</span>' +
                            '<span class="marketplace-review-date">' + rDate + '</span>' +
                        '</div>' +
                        mpStarsHtml(r.rating, true) +
                        (r.text ? '<div class="marketplace-review-text">' + _escBot(r.text) + '</div>' : '') +
                    '</div>' +
                '</div>';
            });
        } else {
            reviewsHtml += '<div style="font-size:12px;color:var(--text3);padding:8px 0;">' + t('bots.noReviewsYet') + '</div>';
        }
        reviewsHtml += '</div>';

        content.innerHTML =
            '<div class="marketplace-detail-header">' +
                '<div class="marketplace-detail-avatar">' + avatarHtml + '</div>' +
                '<div class="marketplace-detail-info">' +
                    '<div class="marketplace-detail-name">' + _escBot(bot.name) + '</div>' +
                    '<div class="marketplace-detail-owner">' + t('bots.byOwner', {name: _escBot(bot.owner_name)}) + '</div>' +
                    '<div class="marketplace-detail-stats">' +
                        '<span class="marketplace-card-cat">' + (_mpCatLabels[bot.category] || bot.category) + '</span>' +
                        '<span>' + mpStarsHtml(bot.rating) + ' <span style="font-size:11px;color:var(--text3);">(' + (bot.rating_count || 0) + ')</span></span>' +
                        '<span><svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:middle;"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> ' + t('bots.installsCount', {count: bot.installs || 0}) + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            (bot.description ? '<div class="marketplace-detail-desc">' + _escBot(bot.description) + '</div>' : '') +
            cmdsHtml +
            miniAppHtml +
            installHtml +
            reviewsHtml;

    } catch (e) {
        content.innerHTML = '<div class="marketplace-empty">' + t('errors.loadError', {message: _escBot(e.message || String(e))}) + '</div>';
    }
};

window.mpBackToList = function() {
    document.getElementById('mp-list-view').style.display = 'flex';
    document.getElementById('mp-detail-view').style.display = 'none';
};

// mpInstallBot defined in settings/bots.js

var _mpSelectedRating = 0;

window.mpSelectStar = function(el, val) {
    _mpSelectedRating = val;
    var container = el.parentElement;
    container.querySelectorAll('.star').forEach(function(s) {
        s.classList.toggle('active', parseInt(s.dataset.val) <= val);
    });
};

window.mpSubmitReview = async function(botId) {
    if (_mpSelectedRating < 1 || _mpSelectedRating > 5) {
        alert(window.t?.('errors.selectRating')||'Select a rating (1-5)');
        return;
    }
    var text = (document.getElementById('mp-review-text')?.value || '').trim();
    try {
        await window.api('POST', '/api/marketplace/' + botId + '/review', {
            rating: _mpSelectedRating,
            text: text
        });
        mpOpenDetail(botId);
    } catch (e) {
        alert((window.t?.('errors.generic')||'Error')+': '+(e.message||e));
    }
};

// ── Report system ──
window.showReportModal = function(userId, messageId) {
    document.getElementById('report-target-id').value = userId || '';
    document.getElementById('report-message-id').value = messageId || '';
    document.getElementById('report-reason').value = 'spam';
    document.getElementById('report-description').value = '';
    var alertEl = document.getElementById('report-alert');
    alertEl.style.display = 'none';
    alertEl.textContent = '';
    document.getElementById('report-submit-btn').disabled = false;
    document.getElementById('report-modal').classList.add('show');
};

window.submitReport = async function() {
    var targetId = document.getElementById('report-target-id').value;
    var messageId = document.getElementById('report-message-id').value;
    var reason = document.getElementById('report-reason').value;
    var description = (document.getElementById('report-description').value || '').trim();
    var alertEl = document.getElementById('report-alert');
    var submitBtn = document.getElementById('report-submit-btn');

    if (!targetId) {
        alertEl.textContent = (window.t?.('errors.userNotSpecified')||'User not specified');
        alertEl.style.display = 'block';
        alertEl.style.color = '#ef4444';
        return;
    }

    submitBtn.disabled = true;
    try {
        var body = { reason: reason, description: description };
        if (messageId) body.message_id = parseInt(messageId);
        var resp = await window.api('POST', '/api/users/report/' + targetId, body);
        alertEl.textContent = resp.message || t('report.reportSent');
        alertEl.style.display = 'block';
        alertEl.style.color = '#22c55e';
        setTimeout(function() {
            document.getElementById('report-modal').classList.remove('show');
        }, 1500);
    } catch (e) {
        alertEl.textContent = e.message || t('report.reportFailed');
        alertEl.style.display = 'block';
        alertEl.style.color = '#ef4444';
        submitBtn.disabled = false;
    }
};

// --- end block ---
