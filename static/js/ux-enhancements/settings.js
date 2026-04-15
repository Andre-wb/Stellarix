import { Haptic } from './core.js';

// ══════════════════════════════════════════════════════════════════════════════
// 13. Bot Store — load, render, search, categories
// ══════════════════════════════════════════════════════════════════════════════

let _botCategory = '';
let _botSearchDebounce = null;

async function loadBotStore() {
    const grid = document.getElementById('bot-store-grid');
    const featured = document.getElementById('bot-featured-grid');
    const empty = document.getElementById('bot-store-empty');
    if (!grid) return;

    try {
        const params = new URLSearchParams();
        if (_botCategory) params.set('category', _botCategory);
        params.set('sort', 'popular');
        const resp = await fetch(`/api/bots/store?${params}`, { credentials: 'include' });
        let bots = [];
        if (resp.ok) bots = (await resp.json()).bots || [];

        if (!bots.length) {
            grid.innerHTML = '';
            if (featured) featured.innerHTML = '';
            if (empty) empty.style.display = 'flex';
            return;
        }
        if (empty) empty.style.display = 'none';

        if (featured && !_botCategory) {
            featured.innerHTML = bots.slice(0, 3).map(b => _renderBotCard(b)).join('');
            const fs = document.getElementById('bot-featured-section');
            if (fs) fs.style.display = '';
        } else {
            const fs = document.getElementById('bot-featured-section');
            if (fs) fs.style.display = 'none';
        }
        grid.innerHTML = bots.map(b => _renderBotCard(b)).join('');
    } catch (e) {
        console.warn('Bot store error:', e);
    }
}

function _renderBotCard(bot) {
    const botSvg = '<svg width="24" height="24" fill="#fff" viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1v3h-1.07A7 7 0 0 1 7.07 19H6v-3h1a7 7 0 0 1 7-7h-1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2M7.5 13A2.5 2.5 0 0 0 5 15.5 2.5 2.5 0 0 0 7.5 18a2.5 2.5 0 0 0 2.5-2.5A2.5 2.5 0 0 0 7.5 13m9 0a2.5 2.5 0 0 0-2.5 2.5 2.5 2.5 0 0 0 2.5 2.5 2.5 2.5 0 0 0 2.5-2.5 2.5 2.5 0 0 0-2.5-2.5"/></svg>';
    const avatar = bot.avatar_url ? `<img src="${_esc(bot.avatar_url)}" style="width:100%;height:100%;border-radius:12px;object-fit:cover;">` : botSvg;
    const starSvg = '<svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>';
    const rating = bot.rating ? starSvg + ' ' + bot.rating.toFixed(1) : '';
    const installs = bot.installs || 0;
    let badges = '';
    if (bot.has_inline) badges += '<span class="bot-badge inline">INLINE</span>';
    if (bot.has_commands) badges += '<span class="bot-badge commands">COMMANDS</span>';
    if (bot.has_mini_app) badges += '<span class="bot-badge miniapp">MINI APP</span>';

    return `<div class="bot-card" onclick="openBotDetail(${bot.id})">
        <div class="bot-card-header">
            <div class="bot-card-avatar">${avatar}</div>
            <div><div class="bot-card-name">${_esc(bot.name)}</div><div class="bot-card-category">${_esc(bot.category || 'other')}</div></div>
        </div>
        <div class="bot-card-desc">${_esc(bot.description || '')}</div>
        ${badges ? '<div class="bot-card-badges">' + badges + '</div>' : ''}
        <div class="bot-card-footer">
            <div class="bot-card-stats">${rating ? '<span>' + rating + '</span>' : ''}<span><svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> ${installs}</span></div>
            <button class="bot-card-install" onclick="event.stopPropagation();installBot(${bot.id})">${window.t ? window.t('bots.install') : 'Install'}</button>
        </div>
    </div>`;
}

function searchBotStore(query) {
    clearTimeout(_botSearchDebounce);
    _botSearchDebounce = setTimeout(async () => {
        const grid = document.getElementById('bot-store-grid');
        if (!grid) return;
        if (!query || query.length < 2) { loadBotStore(); return; }
        try {
            const resp = await fetch(`/api/bots/store?q=${encodeURIComponent(query)}`, { credentials: 'include' });
            if (!resp.ok) return;
            const bots = (await resp.json()).bots || [];
            grid.innerHTML = bots.length ? bots.map(b => _renderBotCard(b)).join('') : `<div style="padding:20px;text-align:center;color:var(--text3);">${window.t ? window.t('bots.noBotsFound') : 'No bots found'}</div>`;
            const fs = document.getElementById('bot-featured-section');
            if (fs) fs.style.display = 'none';
        } catch {}
    }, 300);
}

function filterBotCategory(cat) {
    _botCategory = cat;
    document.querySelectorAll('#bot-categories .cs-folder-tab').forEach(b => b.classList.toggle('active', (b.dataset.cat || '') === cat));
    loadBotStore();
    Haptic.selection();
}

async function installBot(botId) {
    Haptic.success();
    if (window.mpInstallBot) {
        window.mpInstallBot(botId);
        return;
    }
    try {
        const detail = await window.api('GET', '/api/marketplace/' + botId);
        const botUserId = detail.user_id;
        if (window.closeModal) window.closeModal('settings-modal');
        if (botUserId && window.openDM) window.openDM(botUserId);
    } catch (e) {
        window.showToast?.('Error: ' + e.message, 'error');
    }
}

async function openBotDetail(botId) {
    Haptic.light();
    // Fetch bot details + reviews
    try {
        const [detResp, revResp] = await Promise.all([
            fetch(`/api/marketplace/${botId}`, { credentials: 'include' }),
            fetch(`/api/marketplace/${botId}/reviews?limit=10`, { credentials: 'include' }),
        ]);
        if (!detResp.ok) { window.showToast?.('Bot not found', 'error'); return; }
        const bot = await detResp.json();
        const revData = revResp.ok ? await revResp.json() : { reviews: [] };

        // Build fullscreen page as a single fixed div (no nested fixed-in-fixed)
        const page = document.createElement('div');
        page.className = 'bot-detail-card';

        const starFull = '\u2605';
        const starEmpty = '\u2606';
        const stars = (n) => starFull.repeat(Math.round(n || 0)) + starEmpty.repeat(5 - Math.round(n || 0));

        // Close button
        const closeBtn = document.createElement('button');
        closeBtn.className = 'bd-close';
        closeBtn.textContent = '\u00D7';
        closeBtn.addEventListener('click', () => page.remove());
        page.appendChild(closeBtn);

        // Hero
        const hero = document.createElement('div');
        hero.className = 'bd-hero';
        const avatarEl = document.createElement('div');
        avatarEl.className = 'bd-avatar';
        if (bot.avatar_url) {
            const img = document.createElement('img');
            img.src = bot.avatar_url;
            img.style.cssText = 'width:72px;height:72px;border-radius:16px;object-fit:cover;';
            avatarEl.appendChild(img);
        } else {
            avatarEl.style.cssText = 'width:72px;height:72px;border-radius:16px;background:var(--accent);display:flex;align-items:center;justify-content:center;';
            avatarEl.textContent = '\uD83E\uDD16';
            avatarEl.style.fontSize = '32px';
        }
        hero.appendChild(avatarEl);
        const heroInfo = document.createElement('div');
        heroInfo.className = 'bd-hero-info';
        const nameEl = document.createElement('div');
        nameEl.className = 'bd-name';
        nameEl.textContent = bot.name;
        heroInfo.appendChild(nameEl);
        const authorEl = document.createElement('div');
        authorEl.className = 'bd-author';
        authorEl.textContent = 'by ' + (bot.owner_name || 'Unknown');
        heroInfo.appendChild(authorEl);
        const catEl = document.createElement('div');
        catEl.className = 'bd-category';
        catEl.textContent = (bot.category || 'other').toUpperCase();
        heroInfo.appendChild(catEl);
        hero.appendChild(heroInfo);
        page.appendChild(hero);

        // Stats
        const statsRow = document.createElement('div');
        statsRow.className = 'bd-stats-row';
        const stat1 = document.createElement('div');
        stat1.className = 'bd-stat';
        const stat1Val = document.createElement('div');
        stat1Val.className = 'bd-stat-val';
        stat1Val.textContent = stars(bot.rating);
        stat1.appendChild(stat1Val);
        const stat1Label = document.createElement('div');
        stat1Label.className = 'bd-stat-label';
        stat1Label.textContent = (bot.rating || 0).toFixed(1) + ' (' + (bot.rating_count || 0) + ')';
        stat1.appendChild(stat1Label);
        statsRow.appendChild(stat1);
        const stat2 = document.createElement('div');
        stat2.className = 'bd-stat';
        const stat2Val = document.createElement('div');
        stat2Val.className = 'bd-stat-val';
        stat2Val.id = 'bd-installs';
        stat2Val.textContent = String(bot.installs || 0);
        stat2.appendChild(stat2Val);
        const stat2Label = document.createElement('div');
        stat2Label.className = 'bd-stat-label';
        stat2Label.textContent = 'Downloads';
        stat2.appendChild(stat2Label);
        statsRow.appendChild(stat2);
        page.appendChild(statsRow);

        // Description
        const descSection = document.createElement('div');
        descSection.className = 'bd-section';
        const descTitle = document.createElement('div');
        descTitle.className = 'bd-section-title';
        descTitle.textContent = 'Description';
        descSection.appendChild(descTitle);
        const descText = document.createElement('div');
        descText.className = 'bd-desc';
        descText.textContent = bot.description || 'No description';
        descSection.appendChild(descText);
        page.appendChild(descSection);

        // Commands
        const cmdSection = document.createElement('div');
        cmdSection.className = 'bd-section';
        const cmdTitle = document.createElement('div');
        cmdTitle.className = 'bd-section-title';
        cmdTitle.textContent = 'Commands';
        cmdSection.appendChild(cmdTitle);
        (bot.commands || []).forEach(c => {
            const row = document.createElement('div');
            row.className = 'bd-cmd';
            const cmdName = document.createElement('span');
            cmdName.className = 'bd-cmd-name';
            cmdName.textContent = '/' + (c.command || c.name || '');
            row.appendChild(cmdName);
            const cmdDesc = document.createElement('span');
            cmdDesc.className = 'bd-cmd-desc';
            cmdDesc.textContent = c.description || '';
            row.appendChild(cmdDesc);
            cmdSection.appendChild(row);
        });
        if (!bot.commands?.length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:13px;';
            empty.textContent = 'No commands';
            cmdSection.appendChild(empty);
        }
        page.appendChild(cmdSection);

        // Reviews
        const revSection = document.createElement('div');
        revSection.className = 'bd-section';
        const revTitle = document.createElement('div');
        revTitle.className = 'bd-section-title';
        revTitle.textContent = 'Reviews';
        revSection.appendChild(revTitle);
        (revData.reviews || []).forEach(r => {
            const rev = document.createElement('div');
            rev.className = 'bd-review';
            const revHeader = document.createElement('div');
            revHeader.className = 'bd-review-header';
            const revUser = document.createElement('span');
            revUser.className = 'bd-review-user';
            revUser.textContent = r.username || 'User';
            revHeader.appendChild(revUser);
            const revStars = document.createElement('span');
            revStars.className = 'bd-review-stars';
            revStars.textContent = stars(r.rating);
            revHeader.appendChild(revStars);
            rev.appendChild(revHeader);
            if (r.text) {
                const revText = document.createElement('div');
                revText.className = 'bd-review-text';
                revText.textContent = r.text;
                rev.appendChild(revText);
            }
            revSection.appendChild(rev);
        });
        if (!(revData.reviews || []).length) {
            const empty = document.createElement('div');
            empty.style.cssText = 'color:var(--text3);font-size:13px;padding:8px 0;';
            empty.textContent = 'No reviews yet';
            revSection.appendChild(empty);
        }
        page.appendChild(revSection);

        // Install button
        const installBtn = document.createElement('button');
        installBtn.className = 'bd-install-btn';
        installBtn.textContent = 'Install Bot';
        installBtn.addEventListener('click', () => installBot(bot.bot_id));
        page.appendChild(installBtn);

        document.body.appendChild(page);
        // Escape key
        const _escHandler = (e) => { if (e.key === 'Escape') { page.remove(); document.removeEventListener('keydown', _escHandler); } };
        document.addEventListener('keydown', _escHandler);
    } catch (e) {
        window.showToast?.('Error loading bot: ' + e.message, 'error');
    }
}

window.loadBotStore = loadBotStore;
window.searchBotStore = searchBotStore;
window.filterBotCategory = filterBotCategory;
window.installBot = installBot;
window.openBotDetail = openBotDetail;


// ══════════════════════════════════════════════════════════════════════════════
// 14. Settings fullscreen view — sections, language picker
// ══════════════════════════════════════════════════════════════════════════════

const ALL_LANGUAGES = [
    {code:"af",name:"Afrikaans"},{code:"ak",name:"Akan"},{code:"am",name:"አማርኛ"},
    {code:"ar",name:"العربية"},{code:"ay",name:"Aymar aru"},{code:"az",name:"Azərbaycan"},
    {code:"be",name:"Беларуская"},{code:"bg",name:"Български"},{code:"bho",name:"भोजपुरी"},
    {code:"bn",name:"বাংলা"},{code:"bs",name:"Bosanski"},{code:"ca",name:"Català"},
    {code:"ckb",name:"کوردیی ناوەندی"},{code:"co",name:"Corsu"},{code:"cs",name:"Čeština"},
    {code:"cy",name:"Cymraeg"},{code:"da",name:"Dansk"},{code:"de",name:"Deutsch"},
    {code:"doi",name:"डोगरी"},{code:"dv",name:"ދިވެހި"},{code:"ee",name:"Eʋegbe"},
    {code:"el",name:"Ελληνικά"},{code:"en",name:"English"},{code:"eo",name:"Esperanto"},
    {code:"es",name:"Español"},{code:"et",name:"Eesti"},{code:"eu",name:"Euskara"},
    {code:"fa",name:"فارسی"},{code:"fi",name:"Suomi"},{code:"fr",name:"Français"},
    {code:"fy",name:"Frysk"},{code:"ga",name:"Gaeilge"},{code:"gd",name:"Gàidhlig"},
    {code:"gl",name:"Galego"},{code:"gu",name:"ગુજરાતી"},{code:"ha",name:"Hausa"},
    {code:"he",name:"עברית"},{code:"hi",name:"हिन्दी"},{code:"hmn",name:"Hmong"},
    {code:"hr",name:"Hrvatski"},{code:"hu",name:"Magyar"},{code:"hy",name:"Հայերեն"},
    {code:"id",name:"Bahasa Indonesia"},{code:"ilo",name:"Ilokano"},{code:"is",name:"Íslenska"},
    {code:"it",name:"Italiano"},{code:"ja",name:"日本語"},{code:"ka",name:"ქართული"},
    {code:"kk",name:"Қазақша"},{code:"km",name:"ភាសាខ្មែរ"},{code:"kn",name:"ಕನ್ನಡ"},
    {code:"ko",name:"한국어"},{code:"kri",name:"Krio"},{code:"ku",name:"Kurdî"},
    {code:"ky",name:"Кыргызча"},{code:"lt",name:"Lietuvių"},{code:"lus",name:"Mizo ṭawng"},
    {code:"lv",name:"Latviešu"},{code:"mk",name:"Македонски"},{code:"ml",name:"മലയാളം"},
    {code:"mn",name:"Монгол"},{code:"mr",name:"मराठी"},{code:"ms",name:"Bahasa Melayu"},
    {code:"my",name:"မြန်မာ"},{code:"ne",name:"नेपाली"},{code:"nl",name:"Nederlands"},
    {code:"no",name:"Norsk"},{code:"nso",name:"Sepedi"},{code:"ny",name:"Chichewa"},
    {code:"pa",name:"ਪੰਜਾਬੀ"},{code:"pl",name:"Polski"},{code:"pt",name:"Português"},
    {code:"ro",name:"Română"},{code:"ru",name:"Русский"},{code:"si",name:"සිංහල"},
    {code:"sk",name:"Slovenčina"},{code:"sl",name:"Slovenščina"},{code:"sm",name:"Gagana Sāmoa"},
    {code:"so",name:"Soomaali"},{code:"sq",name:"Shqip"},{code:"sr",name:"Српски"},
    {code:"st",name:"Sesotho"},{code:"sv",name:"Svenska"},{code:"sw",name:"Kiswahili"},
    {code:"ta",name:"தமிழ்"},{code:"te",name:"తెలుగు"},{code:"tg",name:"Тоҷикӣ"},
    {code:"th",name:"ไทย"},{code:"ti",name:"ትግርኛ"},{code:"tk",name:"Türkmen"},
    {code:"tl",name:"Filipino"},{code:"tr",name:"Türkçe"},{code:"uk",name:"Українська"},
    {code:"ur",name:"اردو"},{code:"uz",name:"Oʻzbek"},{code:"vi",name:"Tiếng Việt"},
    {code:"yi",name:"ייִדיש"},{code:"zh",name:"中文"},{code:"zh-TW",name:"繁體中文"},
    {code:"zu",name:"isiZulu"},
].sort((a,b) => a.name.localeCompare(b.name));

function openSettingsView() {
    // Populate profile card
    const S = window.AppState;
    if (S && S.user) {
        const av = document.getElementById('set-avatar');
        const nm = document.getElementById('set-name');
        const ph = document.getElementById('set-phone');
        if (av) {
            if (S.user.avatar_emoji) { av.textContent = S.user.avatar_emoji; }
            else { av.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="currentColor" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>'; }
        }
        if (nm) nm.textContent = S.user.display_name || S.user.username || '—';
        if (ph) ph.textContent = S.user.phone || S.user.username || '—';
    }
    // Render multi-account section in settings
    _renderSettingsAccounts();

    // Show current language
    const langVal = document.getElementById('set-current-lang');
    const currentLang = window.getLocale ? window.getLocale() : 'en';
    const langObj = ALL_LANGUAGES.find(l => l.code === currentLang);
    if (langVal) langVal.textContent = langObj ? langObj.name : currentLang;

    // Show main list, hide sub-pages
    const main = document.getElementById('settings-main-list');
    const sub = document.getElementById('settings-sub-page');
    const lang = document.getElementById('settings-lang-page');
    if (main) main.style.display = '';
    if (sub) sub.style.display = 'none';
    if (lang) lang.style.display = 'none';
}

function openSettingsSection(section) {
    if (section === 'language') {
        document.getElementById('settings-main-list').style.display = 'none';
        document.getElementById('settings-lang-page').style.display = 'flex';
        renderLanguageList('');
        const input = document.getElementById('lang-search-input');
        if (input) { input.value = ''; input.focus(); }
        Haptic.light();
        return;
    }

    const sectionEl = document.getElementById('settings-' + section);
    const content   = document.getElementById('settings-sub-content');
    const sub       = document.getElementById('settings-sub-page');
    const main      = document.getElementById('settings-main-list');
    const titleEl   = document.getElementById('settings-sub-title');
    const pool      = document.getElementById('settings-sections-pool');

    if (!sectionEl || !content || !sub || !pool) return;

    // Return any previously open section back to the pool
    while (content.firstChild) pool.appendChild(content.firstChild);

    // Move section into sub-page and make it visible
    sectionEl.classList.add('active');
    content.appendChild(sectionEl);

    // Set localised title
    const titles = {
        profile:       window.t ? window.t('settings.profile')       : 'Profile',
        security:      window.t ? window.t('settings.security')      : 'Security',
        appearance:    window.t ? window.t('settings.appearance')    : 'Appearance',
        notifications: window.t ? window.t('settings.notifications') : 'Notifications',
        storage:       window.t ? window.t('settings.storage')       : 'Storage',
        calls:         window.t ? window.t('settings.calls')         : 'Calls',
        stickers:      window.t ? window.t('settings.stickers')      : 'Stickers',
        bots:          window.t ? window.t('settings.bots')          : 'Bots',
        about:         window.t ? window.t('settings.about')         : 'About',
        privacy:       window.t ? window.t('settings.privacy')       : 'Privacy',
        sessions:      window.t ? window.t('settings.sessions')      : 'Sessions',
        federation:    window.t ? window.t('settings.federation')    : 'Federation',
        dev:           window.t ? window.t('settings.devSettings')   : 'Dev Settings',
        panic:         window.t ? window.t('settings.panic')         : 'Panic',
    };
    if (titleEl) titleEl.textContent = titles[section] || section;

    if (main) main.style.display = 'none';
    sub.style.display = 'flex';
    Haptic.light();

    // Section-specific initialization
    const S = window.AppState;
    if (section === 'profile' && S?.user) {
        const dn = document.getElementById('set-display-name');
        const em = document.getElementById('set-email');
        if (dn) dn.value = S.user.display_name || '';
        if (em) em.value = S.user.email || '';
        const av = document.getElementById('settings-avatar');
        if (av) {
            if (S.user.avatar_url) {
                av.innerHTML = `<img src="${S.user.avatar_url}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
            } else {
                if (S.user.avatar_emoji) { av.textContent = S.user.avatar_emoji; }
                else { av.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="currentColor" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>'; }
            }
        }
        window._settingsSelectedEmoji = null;
        document.querySelectorAll('#settings-emoji-picker .emoji-btn').forEach(b => {
            b.classList.remove('emoji-selected');
            if (b.dataset.emoji === S.user.avatar_emoji) b.classList.add('emoji-selected');
        });

        // Bio
        const bioEl = document.getElementById('set-bio');
        if (bioEl) {
            bioEl.value = S.user.bio || '';
            const counter = document.getElementById('set-bio-count');
            if (counter) counter.textContent = bioEl.value.length;
            bioEl.oninput = () => { if (counter) counter.textContent = bioEl.value.length; };
        }

        // Birthday
        const bdBtn  = document.getElementById('set-birthday-btn');
        const bdText = document.getElementById('set-birthday-text');
        if (bdBtn && bdText) {
            const bd = S.user.birth_date || '';
            bdBtn.dataset.value = bd;
            if (bd) {
                const MONTHS_GEN = window.t ? window.t('time.monthsGen') : ['January','February','March','April','May','June','July','August','September','October','November','December'];
                try {
                    if (bd.startsWith('--')) {
                        const [m, d] = bd.slice(2).split('-').map(Number);
                        bdText.textContent = d + ' ' + (Array.isArray(MONTHS_GEN) ? MONTHS_GEN[m - 1] : bd);
                    } else {
                        const [y, m, d] = bd.split('-').map(Number);
                        bdText.textContent = d + '.' + String(m).padStart(2,'0') + '.' + y;
                    }
                } catch { bdText.textContent = bd; }
            } else {
                bdText.textContent = window.t ? window.t('settings.birthdayNotSet') : 'Not set';
            }
        }

        // Profile background
        const currentBg = S.user.profile_bg || 'linear-gradient(135deg,#0f0c29,#302b63,#24243e)';
        window._settingsProfileBg = currentBg;
        document.querySelectorAll('.pbg-swatch').forEach(b => {
            const match = b.dataset.bg === currentBg;
            b.classList.toggle('active', match);
        });
        const bgPreview = document.getElementById('set-profile-bg-preview');
        if (bgPreview) bgPreview.style.background = currentBg;

        // Profile icon
        const currentIcon = S.user.profile_icon || '';
        window._settingsProfileIcon = currentIcon || undefined;
        document.querySelectorAll('.pi-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.icon === currentIcon);
        });
        // Sync mini preview
        const piSvg  = document.getElementById('pi-preview-svg');
        const piHero = document.getElementById('pi-preview-hero');
        if (piSvg && window._PROFILE_ICONS) {
            const paths = window._PROFILE_ICONS[currentIcon] || '';
            piSvg.innerHTML    = paths;
            piSvg.style.display = paths ? '' : 'none';
        }
        if (piHero) {
            const bg = S.user.profile_bg || 'linear-gradient(135deg,#0f0c29,#302b63,#24243e)';
            piHero.style.background = bg;
        }
    }
    if (section === 'security' && S?.user) {
        const pk = document.getElementById('settings-pubkey');
        if (pk) pk.textContent = S.user.x25519_public_key || '-';
        if (typeof window._loadPinStatus === 'function') window._loadPinStatus();
        if (typeof window._load2FAStatus === 'function') window._load2FAStatus();
        _updatePwChangeWarning();
    }
    if (section === 'appearance') {
        if (typeof window._highlightActiveTheme === 'function') window._highlightActiveTheme();
        if (typeof window._highlightActiveAccent === 'function') window._highlightActiveAccent();
        if (typeof window._highlightLang === 'function') window._highlightLang();
        if (typeof window._renderFontPicker === 'function') window._renderFontPicker();
        // Init font size slider
        const slider = document.getElementById('font-size-slider');
        const savedSize = localStorage.getItem('vortex_font_size') || '15';
        if (slider) { slider.value = savedSize; }
        const sizeLabel = document.getElementById('font-size-value');
        if (sizeLabel) sizeLabel.textContent = savedSize + 'px';
        // Show custom font name if loaded
        const customFontName = localStorage.getItem('vortex_custom_font_name');
        const nameEl = document.getElementById('custom-font-name');
        if (nameEl && customFontName) nameEl.textContent = customFontName;
    }
    if (section === 'sessions') {
        if (typeof window._loadSessions === 'function') window._loadSessions();
        _loadSessionLimit();
    }
    if (section === 'storage') {
        if (typeof _updateStorageUI === 'function') _updateStorageUI();
    }
    if (section === 'calls') {
        if (typeof window._loadCallSettings === 'function') window._loadCallSettings();
        if (typeof window._loadDeviceSettings === 'function') window._loadDeviceSettings();
    }
    if (section === 'stickers') {
        if (typeof window.loadStickerManager === 'function') window.loadStickerManager();
    }
    if (section === 'bots') {
        if (typeof window.loadMyBots === 'function') window.loadMyBots();
    }
    if (section === 'privacy') {
        if (typeof window._loadPrivacySettings === 'function') window._loadPrivacySettings();
        _loadSQStatus();
        _loadShowLastSeen();
        _loadBMPSetting();
    }
    if (section === 'federation') {
        if (typeof window.initFederationSettings === 'function') window.initFederationSettings();
    }
    if (section === 'dev') {
        if (typeof window.DevSettings?.renderDevSettings === 'function') {
            window.DevSettings.renderDevSettings();
            // update theme count badge
            const badge = document.getElementById('dev-theme-count');
            if (badge && window.DevSettings.themes) badge.textContent = window.DevSettings.themes.length + ' themes';
        }
    }
}

function closeSettingsLangPage() {
    document.getElementById('settings-lang-page').style.display = 'none';
    document.getElementById('settings-main-list').style.display = '';
}

function closeSettingsSubPage() {
    const sub     = document.getElementById('settings-sub-page');
    const main    = document.getElementById('settings-main-list');
    const content = document.getElementById('settings-sub-content');
    const pool    = document.getElementById('settings-sections-pool');

    // Cleanup federation auto-refresh
    if (typeof window.cleanupFederationSettings === 'function') window.cleanupFederationSettings();

    // Return section back to pool
    if (content && pool) {
        while (content.firstChild) {
            const el = content.firstChild;
            el.classList.remove('active');
            pool.appendChild(el);
        }
    }

    if (sub) sub.style.display = 'none';
    if (main) main.style.display = '';
}

function renderLanguageList(query) {
    const list = document.getElementById('lang-list');
    if (!list) return;
    const currentLang = window.getLocale ? window.getLocale() : 'en';
    const q = (query || '').toLowerCase();

    const filtered = q
        ? ALL_LANGUAGES.filter(l => l.name.toLowerCase().includes(q) || l.code.toLowerCase().includes(q))
        : ALL_LANGUAGES;

    list.innerHTML = filtered.map(l => {
        const isActive = l.code === currentLang;
        return `<div class="lang-item${isActive ? ' active' : ''}" onclick="selectLanguage('${l.code}')">
            <div class="lang-check"></div>
            <span class="lang-native">${l.name}</span>
            <span class="lang-code">${l.code}</span>
        </div>`;
    }).join('');
}

function filterLanguages(query) {
    renderLanguageList(query);
}

async function selectLanguage(code) {
    if (window.setLocale) await window.setLocale(code);
    Haptic.medium();
    renderLanguageList('');
    // Update label
    const langVal = document.getElementById('set-current-lang');
    const langObj = ALL_LANGUAGES.find(l => l.code === code);
    if (langVal) langVal.textContent = langObj ? langObj.name : code;
    // Update select in old settings modal too
    const sel = document.getElementById('lang-select');
    if (sel) sel.value = code;
}

window.openSettingsView = openSettingsView;
window.openSettingsSection = openSettingsSection;
window.closeSettingsLangPage = closeSettingsLangPage;
window.closeSettingsSubPage = closeSettingsSubPage;
window.filterLanguages = filterLanguages;
window.selectLanguage = selectLanguage;


// ══════════════════════════════════════════════════════════════════════════════
// Sessions — active devices, terminate, auto-delete account
// ══════════════════════════════════════════════════════════════════════════════

async function _loadSessions() {
    const list = document.getElementById('sessions-list');
    const terminateBtn = document.getElementById('sessions-terminate-all');
    if (!list) return;
    list.innerHTML = '<div class="sessions-loading">...</div>';

    try {
        const resp = await fetch('/api/authentication/devices', { credentials: 'include' });
        if (!resp.ok) throw new Error(resp.statusText);
        const data = await resp.json();
        const devices = data.devices || [];

        if (devices.length === 0) {
            list.innerHTML = '<div class="sessions-loading">No active sessions</div>';
            if (terminateBtn) terminateBtn.style.display = 'none';
            return;
        }

        const canManage = data.can_manage === true;
        const hasOthers = devices.filter(d => !d.is_current).length > 0;

        list.innerHTML = devices.map(d => {
            const icon = d.device_type === 'mobile'
                ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>'
                : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>';
            const isCurrent = d.is_current;
            const date = d.last_active ? new Date(d.last_active).toLocaleDateString() : '';
            const ip = d.ip_address || '';
            return `<div class="session-card${isCurrent ? ' current' : ''}">
                <div class="session-icon">${icon}</div>
                <div class="session-info">
                    <div class="session-name">${_esc(d.device_name || 'Unknown')}</div>
                    <div class="session-meta">
                        ${ip ? `<span>${ip}</span>` : ''}
                        ${date ? `<span>${date}</span>` : ''}
                        ${isCurrent ? `<span class="session-current-badge">${window.t ? window.t('settings.currentSession') : 'this device'}</span>` : ''}
                    </div>
                </div>
                ${!isCurrent && canManage ? `<button class="session-close" onclick="window._terminateSession(${d.id})" title="Terminate">
                    <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                </button>` : ''}
            </div>`;
        }).join('');

        // Warning if session too young
        if (!canManage && hasOthers) {
            list.innerHTML += `<div class="session-age-warning">
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
                <span>${window.t ? window.t('settings.sessionTooYoung') : 'Your session must be at least 7 days old to manage other sessions'}</span>
            </div>`;
        }

        if (terminateBtn) {
            terminateBtn.style.display = hasOthers && canManage ? 'flex' : 'none';
        }
    } catch (e) {
        list.innerHTML = `<div class="sessions-loading" style="color:var(--red);">Error: ${e.message}</div>`;
    }

    // Restore TTL state
    _restoreTTLState();
}

async function _terminateSession(deviceId) {
    try {
        await fetch(`/api/authentication/devices/${deviceId}`, { method: 'DELETE', credentials: 'include' });
        _loadSessions();
        if (typeof window.showToast === 'function') window.showToast(window.t ? window.t('settings.sessionTerminated') : 'Session terminated', 'success');
    } catch (e) {
        console.error('terminate session error:', e);
    }
}

async function _terminateAllSessions() {
    try {
        await fetch('/api/authentication/devices', { method: 'DELETE', credentials: 'include' });
        _loadSessions();
        if (typeof window.showToast === 'function') window.showToast(window.t ? window.t('settings.allSessionsTerminated') : 'All other sessions terminated', 'success');
    } catch (e) {
        console.error('terminate all error:', e);
    }
}

function _setAccountTTL(days) {
    localStorage.setItem('vortex_account_ttl', String(days));
    _highlightTTLBtn(days);
    const status = document.getElementById('account-ttl-status');
    if (status) {
        if (days === 0) {
            status.textContent = window.t ? window.t('settings.ttlDisabled') : 'Auto-delete disabled';
        } else {
            status.textContent = (window.t ? window.t('settings.ttlSet') : 'Account will be deleted after') + ` ${days} ` + (window.t ? window.t('settings.daysInactive') : 'days of inactivity');
        }
    }
    // Save to server
    fetch('/api/authentication/account-ttl', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ttl_days: days }),
    }).catch(() => {});
}

async function _showCustomTTLModal() {
    const val = await window.vxPrompt?.(t('settings.ttlPrompt'), '30', t('settings.ttlDaysLabel'));
    if (val === null) return;
    const days = parseInt(val);
    if (isNaN(days) || days < 1) return;
    _setAccountTTL(days);
}

function _saveCustomTTL() {
    const val = parseInt(document.getElementById('custom-ttl-value')?.value || '14', 10);
    const unit = document.getElementById('custom-ttl-unit')?.value || 'days';
    let days = val;
    if (unit === 'weeks') days = val * 7;
    else if (unit === 'months') days = val * 30;
    else if (unit === 'years') days = val * 365;
    _setAccountTTL(days);
    const modal = document.getElementById('custom-ttl-modal');
    if (modal) modal.style.display = 'none';
}

function _highlightTTLBtn(days) {
    document.querySelectorAll('.auto-delete-btn').forEach(btn => {
        const v = btn.dataset.ttl;
        btn.classList.toggle('active', String(days) === v);
    });
}

function _restoreTTLState() {
    const saved = localStorage.getItem('vortex_account_ttl');
    if (saved !== null) {
        const days = parseInt(saved, 10);
        _highlightTTLBtn(days);
        const status = document.getElementById('account-ttl-status');
        if (status) {
            if (days === 0) {
                status.textContent = window.t ? window.t('settings.ttlDisabled') : 'Auto-delete disabled';
            } else {
                status.textContent = (window.t ? window.t('settings.ttlSet') : 'Account will be deleted after') + ` ${days} ` + (window.t ? window.t('settings.daysInactive') : 'days of inactivity');
            }
        }
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Security Questions Setup Modal (onboarding + privacy settings)
// ══════════════════════════════════════════════════════════════════════════════

function _getDefaultQuestions() {
    return [
        t('settings.sqQuestion1'),
        t('settings.sqQuestion2'),
        t('settings.sqQuestion3'),
    ];
}

function _showSecurityQuestionsSetup() {
    let existing = document.getElementById('sq-setup-modal');
    if (existing) { existing.style.display = 'flex'; return; }

    const modal = document.createElement('div');
    modal.id = 'sq-setup-modal';
    modal.className = 'custom-ttl-modal';
    modal.style.display = 'flex';
    modal.onclick = (e) => { if (e.target === modal) modal.style.display = 'none'; };

    modal.innerHTML = `
        <div class="custom-ttl-card" style="max-width:380px;width:90%;">
            <div style="text-align:center;margin-bottom:16px;">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
            </div>
            <div class="custom-ttl-title" style="text-align:center;">${t('settings.sqSetupTitle')}</div>
            <p style="font-size:12px;color:var(--text2);text-align:center;margin-bottom:16px;line-height:1.5;">
                ${t('settings.sqSetupDesc')}
            </p>
            <div style="display:flex;flex-direction:column;gap:10px;" id="sq-setup-fields">
                ${_getDefaultQuestions().map((q, i) => `
                    <div>
                        <input class="form-input sq-setup-q" type="text" value="${q}" placeholder="${t('settings.sqQuestionPlaceholder', {n: i+1})}" style="margin-bottom:4px;font-size:12px;">
                        <input class="form-input sq-setup-a" type="text" placeholder="${t('settings.sqAnswerPlaceholder', {n: i+1})}" style="font-size:13px;">
                    </div>
                `).join('')}
            </div>
            <div class="custom-ttl-actions" style="margin-top:14px;">
                <button class="custom-ttl-save" onclick="window._saveSecurityQuestions()">${t('settings.save')}</button>
                <button class="custom-ttl-cancel" onclick="document.getElementById('sq-setup-modal').style.display='none';localStorage.setItem('vortex_sq_done','skipped')">${t('settings.later')}</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

async function _saveSecurityQuestions() {
    const qs = Array.from(document.querySelectorAll('.sq-setup-q')).map(i => i.value.trim());
    const as_ = Array.from(document.querySelectorAll('.sq-setup-a')).map(i => i.value.trim());

    if (qs.some(q => !q) || as_.some(a => !a)) {
        if (typeof window.showToast === 'function') window.showToast(t('settings.sqFillAll'), 'error');
        return;
    }

    try {
        const resp = await fetch('/api/authentication/security-questions/setup', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ questions: qs, answers: as_ }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || resp.statusText);
        }
        localStorage.setItem('vortex_sq_done', '1');
        const modal = document.getElementById('sq-setup-modal');
        if (modal) modal.style.display = 'none';
        if (typeof window.showToast === 'function') window.showToast(t('settings.sqSaved'), 'success');
    } catch (e) {
        if (typeof window.showToast === 'function') window.showToast(t('errors.generic', {message: e.message}), 'error');
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Monthly Password Reminder
// ══════════════════════════════════════════════════════════════════════════════

function _showPasswordReminder() {
    let existing = document.getElementById('pw-reminder-modal');
    if (existing) { existing.style.display = 'flex'; return; }

    const modal = document.createElement('div');
    modal.id = 'pw-reminder-modal';
    modal.className = 'custom-ttl-modal';
    modal.style.display = 'flex';

    modal.innerHTML = `
        <div class="custom-ttl-card" style="max-width:360px;width:90%;">
            <div style="text-align:center;margin-bottom:14px;">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
            </div>
            <div class="custom-ttl-title" style="text-align:center;font-size:16px;">${t('settings.pwReminderTitle')}</div>
            <p style="font-size:12px;color:var(--text2);text-align:center;margin:10px 0 16px;line-height:1.5;">
                ${t('settings.pwReminderDesc')}
            </p>
            <div style="display:flex;flex-direction:column;gap:8px;">
                <button class="custom-ttl-save" style="background:var(--green,#22c55e);" onclick="window._pwReminderYes()">${t('settings.pwYesRemember')}</button>
                <button class="custom-ttl-save" style="background:var(--yellow,#eab308);color:#000;" onclick="window._pwReminderTest()">${t('settings.pwNotSureCheck')}</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function _pwReminderYes() {
    localStorage.setItem('vortex_pw_check_ts', String(Date.now()));
    const modal = document.getElementById('pw-reminder-modal');
    if (modal) modal.remove();
}

function _pwReminderTest() {
    const modal = document.getElementById('pw-reminder-modal');
    if (modal) modal.innerHTML = `
        <div class="custom-ttl-card" style="max-width:360px;width:90%;">
            <div class="custom-ttl-title" style="text-align:center;font-size:16px;">${t('settings.pwEnterCurrent')}</div>
            <div style="margin:14px 0;">
                <input class="custom-ttl-input" id="pw-test-input" type="password" placeholder="${t('settings.pwPlaceholder')}" style="width:100%;text-align:left;font-size:14px;">
            </div>
            <div id="pw-test-status" style="font-size:12px;min-height:18px;text-align:center;margin-bottom:10px;"></div>
            <div style="display:flex;gap:8px;">
                <button class="custom-ttl-save" onclick="window._pwTestCheck()">${t('settings.pwVerify')}</button>
                <button class="custom-ttl-cancel" onclick="document.getElementById('pw-reminder-modal').remove()">${t('settings.cancel')}</button>
            </div>
        </div>
    `;
    setTimeout(() => document.getElementById('pw-test-input')?.focus(), 100);
}

async function _pwTestCheck() {
    const input = document.getElementById('pw-test-input');
    const status = document.getElementById('pw-test-status');
    const password = input?.value;
    if (!password) { if (status) status.textContent = t('settings.pwEnterPassword'); return; }

    if (status) { status.textContent = t('settings.pwChecking'); status.style.color = 'var(--text2)'; }

    try {
        const resp = await fetch('/api/authentication/verify-password', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
        const data = await resp.json();
        if (data.valid) {
            localStorage.setItem('vortex_pw_check_ts', String(Date.now()));
            if (status) { status.textContent = t('settings.pwCorrect'); status.style.color = 'var(--green)'; }
            setTimeout(() => document.getElementById('pw-reminder-modal')?.remove(), 1200);
        } else {
            if (status) { status.style.color = 'var(--red)'; }
            const modal = document.getElementById('pw-reminder-modal');
            if (modal) modal.querySelector('.custom-ttl-card').innerHTML = `
                <div style="text-align:center;margin-bottom:14px;">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="1.5"><path d="M12 9v4m0 4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"/></svg>
                </div>
                <div class="custom-ttl-title" style="text-align:center;color:var(--red);font-size:16px;">${t('settings.pwIncorrect')}</div>
                <p style="font-size:12px;color:var(--text2);text-align:center;margin:10px 0 16px;line-height:1.5;">
                    ${t('settings.pwIncorrectDesc')}
                </p>
                <div style="display:flex;flex-direction:column;gap:8px;">
                    <button class="custom-ttl-save" onclick="window._pwShowChange()">${t('settings.pwChange')}</button>
                    <button class="custom-ttl-cancel" onclick="document.getElementById('pw-reminder-modal').remove()">${t('settings.later')}</button>
                </div>
            `;
        }
    } catch (e) {
        if (status) { status.textContent = t('errors.generic', {message: e.message}); status.style.color = 'var(--red)'; }
    }
}

function _pwShowChange() {
    const modal = document.getElementById('pw-reminder-modal');
    if (modal) modal.querySelector('.custom-ttl-card').innerHTML = `
        <div class="custom-ttl-title" style="text-align:center;font-size:16px;">${t('settings.pwNewTitle')}</div>
        <div style="margin:14px 0;display:flex;flex-direction:column;gap:8px;">
            <input class="custom-ttl-input" id="pw-new1" type="password" placeholder="${t('settings.pwNewPlaceholder')}" style="width:100%;text-align:left;font-size:14px;">
            <input class="custom-ttl-input" id="pw-new2" type="password" placeholder="${t('settings.pwRepeatPlaceholder')}" style="width:100%;text-align:left;font-size:14px;">
        </div>
        <div id="pw-change-status" style="font-size:12px;min-height:18px;text-align:center;margin-bottom:10px;"></div>
        <div style="display:flex;gap:8px;">
            <button class="custom-ttl-save" onclick="window._pwDoChange()">${t('settings.save')}</button>
            <button class="custom-ttl-cancel" onclick="document.getElementById('pw-reminder-modal').remove()">${t('settings.cancel')}</button>
        </div>
    `;
    setTimeout(() => document.getElementById('pw-new1')?.focus(), 100);
}

async function _pwDoChange() {
    const p1 = document.getElementById('pw-new1')?.value;
    const p2 = document.getElementById('pw-new2')?.value;
    const status = document.getElementById('pw-change-status');
    if (!p1 || p1.length < 8) { if (status) { status.textContent = t('settings.pwMinChars'); status.style.color = 'var(--red)'; } return; }
    if (p1 !== p2) { if (status) { status.textContent = t('settings.pwMismatch'); status.style.color = 'var(--red)'; } return; }

    try {
        const resp = await fetch('/api/authentication/change-password', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_password: p1 }),
        });
        if (resp.ok) {
            localStorage.setItem('vortex_pw_check_ts', String(Date.now()));
            if (status) { status.textContent = t('settings.pwUpdated'); status.style.color = 'var(--green)'; }
            setTimeout(() => document.getElementById('pw-reminder-modal')?.remove(), 1500);
        } else {
            const err = await resp.json();
            if (status) { status.textContent = err.detail || t('errors.error'); status.style.color = 'var(--red)'; }
        }
    } catch (e) {
        if (status) { status.textContent = e.message; status.style.color = 'var(--red)'; }
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Safe Cache Clear — preserves keys, removes media/temp data
// ══════════════════════════════════════════════════════════════════════════════

const _PROTECTED_PREFIXES = [
    'vortex_rk_',           // room keys (sessionStorage)
    'vortex_x25519',        // X25519 private key
    'vortex_kyber',         // Kyber key
    'vortex_priv',          // private key backup
    'vortex_pub',           // public key
    'vortex_seed',          // seed phrase hash
    'vortex_sq_',           // security questions state
    'vortex_pw_check',      // password check timestamp
    'vortex_font',          // font preference (keep UX)
    'vortex_font_size',     // font size
    'vortex_custom_font',   // custom font data
    'vortex_account_ttl',   // auto-delete setting
    'vortex_last_room',     // last opened room
];

function _isProtectedKey(key) {
    return _PROTECTED_PREFIXES.some(prefix => key.startsWith(prefix));
}

async function _clearCacheSafe() {
    if (!confirm(t('settings.clearCacheConfirm'))) return;

    let cleared = 0;

    // 1. sessionStorage — remove only non-key entries
    const ssKeep = {};
    for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (_isProtectedKey(key)) {
            ssKeep[key] = sessionStorage.getItem(key);
        }
    }
    const ssBefore = sessionStorage.length;
    sessionStorage.clear();
    for (const [k, v] of Object.entries(ssKeep)) {
        sessionStorage.setItem(k, v);
    }
    cleared += ssBefore - Object.keys(ssKeep).length;

    // 2. localStorage — remove only cache/temp entries, keep keys & settings
    const lsToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (!_isProtectedKey(key) && !key.startsWith('vortex_')) {
            // Non-vortex keys (e.g. third-party) — remove
            lsToRemove.push(key);
        }
    }
    lsToRemove.forEach(k => localStorage.removeItem(k));
    cleared += lsToRemove.length;

    // 3. Cache API — clear service worker caches (images, static assets)
    if ('caches' in window) {
        const names = await caches.keys();
        for (const name of names) {
            await caches.delete(name);
            cleared++;
        }
    }

    // 4. IndexedDB — clear media blobs if any
    if ('indexedDB' in window) {
        const dbs = await indexedDB.databases?.() || [];
        for (const db of dbs) {
            if (db.name && !db.name.includes('key') && !db.name.includes('crypto')) {
                indexedDB.deleteDatabase(db.name);
                cleared++;
            }
        }
    }

    // 5. Tell service worker to clear its cache
    navigator.serviceWorker?.controller?.postMessage({ type: 'clear-cache' });

    const info = document.getElementById('cache-size-info');
    if (info) info.textContent = t('settings.clearedItems', {count: cleared});

    if (typeof window.showToast === 'function') {
        window.showToast(t('settings.cacheCleared'), 'success');
    }
}

async function _calcStorageUsage() {
    let mediaBytes = 0, cacheBytes = 0, keysBytes = 0;

    // sessionStorage + localStorage sizes
    for (const store of [sessionStorage, localStorage]) {
        for (let i = 0; i < store.length; i++) {
            const key = store.key(i);
            const size = (key.length + (store.getItem(key) || '').length) * 2; // UTF-16
            if (_isProtectedKey(key)) {
                keysBytes += size;
            } else {
                cacheBytes += size;
            }
        }
    }

    // Cache API
    if ('caches' in window) {
        try {
            const names = await caches.keys();
            for (const name of names) {
                const cache = await caches.open(name);
                const requests = await cache.keys();
                for (const req of requests) {
                    try {
                        const resp = await cache.match(req);
                        if (resp) {
                            const blob = await resp.blob();
                            mediaBytes += blob.size;
                        }
                    } catch {}
                }
            }
        } catch {}
    }

    return { mediaBytes, cacheBytes, keysBytes };
}

function _formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

async function _updateStorageUI() {
    const { mediaBytes, cacheBytes, keysBytes } = await _calcStorageUsage();
    const total = mediaBytes + cacheBytes + keysBytes;

    const totalEl = document.getElementById('storage-total-size');
    if (totalEl) totalEl.textContent = _formatBytes(total) + ' ' + t('settings.storageUsed');

    const mediaEl = document.getElementById('storage-media-size');
    const cacheEl = document.getElementById('storage-cache-size');
    const keysEl = document.getElementById('storage-keys-size');
    if (mediaEl) mediaEl.textContent = _formatBytes(mediaBytes);
    if (cacheEl) cacheEl.textContent = _formatBytes(cacheBytes);
    if (keysEl) keysEl.textContent = _formatBytes(keysBytes);

    // Update bar
    if (total > 0) {
        const m = document.getElementById('sb-media');
        const c = document.getElementById('sb-cache');
        const k = document.getElementById('sb-keys');
        if (m) m.style.width = Math.max(2, (mediaBytes / total) * 100) + '%';
        if (c) c.style.width = Math.max(2, (cacheBytes / total) * 100) + '%';
        if (k) k.style.width = Math.max(2, (keysBytes / total) * 100) + '%';
    }
}

async function _clearCacheCategory(category) {
    if (category === 'media') {
        // Clear Cache API (service worker caches)
        if ('caches' in window) {
            const names = await caches.keys();
            for (const name of names) await caches.delete(name);
        }
        if ('indexedDB' in window) {
            const dbs = await indexedDB.databases?.() || [];
            for (const db of dbs) {
                if (db.name && !db.name.includes('key') && !db.name.includes('crypto')) {
                    indexedDB.deleteDatabase(db.name);
                }
            }
        }
        navigator.serviceWorker?.controller?.postMessage({ type: 'clear-cache' });
    } else if (category === 'cache') {
        // Clear non-protected sessionStorage + localStorage entries
        const ssKeep = {};
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            if (_isProtectedKey(key)) ssKeep[key] = sessionStorage.getItem(key);
        }
        sessionStorage.clear();
        for (const [k, v] of Object.entries(ssKeep)) sessionStorage.setItem(k, v);
    }
    if (typeof window.showToast === 'function') window.showToast(t('settings.cleared'), 'success');
    _updateStorageUI();
}

window._clearCacheSafe = _clearCacheSafe;
window._clearCacheCategory = _clearCacheCategory;

window._showPasswordReminder = _showPasswordReminder;
// Смена пароля со страницы безопасности (проверка can_manage)
async function _secChangePassword() {
    try {
        const resp = await fetch('/api/authentication/devices', { credentials: 'include' });
        const data = await resp.json();
        const canManage = data.can_manage === true;
        if (!canManage) {
            // Найдём текущее устройство и посчитаем оставшиеся дни
            const current = (data.devices || []).find(d => d.is_current);
            let daysLeft = 7;
            if (current?.created_at) {
                const created = new Date(current.created_at);
                const ageDays = (Date.now() - created.getTime()) / (1000 * 60 * 60 * 24);
                daysLeft = Math.ceil(7 - ageDays);
                if (daysLeft < 1) daysLeft = 1;
            }
            window.vxAlert(t('settings.sessionTooYoungForPwChange', {daysLeft: daysLeft}));
            return;
        }
    } catch { /* ignore, let server validate */ }
    _showPasswordChangeModal();
}

function _showPasswordChangeModal() {
    let modal = document.getElementById('pw-reminder-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'pw-reminder-modal';
        modal.className = 'custom-ttl-overlay';
        modal.innerHTML = '<div class="custom-ttl-card"></div>';
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
        document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    _pwShowChange();
}

// Обновим предупреждение на странице безопасности
async function _updatePwChangeWarning() {
    const warn = document.getElementById('pw-change-warning');
    if (!warn) return;
    try {
        const resp = await fetch('/api/authentication/devices', { credentials: 'include' });
        const data = await resp.json();
        const canManage = data.can_manage === true;
        if (canManage) {
            warn.textContent = '';
        } else {
            const current = (data.devices || []).find(d => d.is_current);
            let daysLeft = 7;
            if (current?.created_at) {
                const created = new Date(current.created_at);
                const ageDays = (Date.now() - created.getTime()) / (1000 * 60 * 60 * 24);
                daysLeft = Math.ceil(7 - ageDays);
                if (daysLeft < 1) daysLeft = 1;
            }
            warn.textContent = t('settings.waitDaysWarning', {daysLeft: daysLeft});
            warn.style.color = 'var(--yellow, #f59e0b)';
        }
    } catch { }
}

window._secChangePassword = _secChangePassword;
window._pwReminderYes = _pwReminderYes;
window._pwReminderTest = _pwReminderTest;
window._pwTestCheck = _pwTestCheck;
window._pwShowChange = _pwShowChange;
window._pwDoChange = _pwDoChange;

async function _loadSQStatus() {
    const status = document.getElementById('sq-settings-status');
    const btn = document.getElementById('sq-settings-btn');
    if (!status) return;
    try {
        const username = window.AppState?.user?.username;
        if (!username) { status.textContent = t('settings.notAuthorized'); return; }
        const resp = await fetch('/api/authentication/security-questions/load', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username }),
        });
        const data = await resp.json();
        if (data.questions?.length === 3) {
            status.innerHTML = '<span style="color:var(--green);">' + t('settings.sqConfigured') + '</span>';
            if (btn) btn.textContent = t('settings.sqChangeQuestions');
        } else {
            status.innerHTML = '<span style="color:var(--yellow);">' + t('settings.sqNotConfigured') + '</span>';
            if (btn) btn.textContent = t('settings.sqSetupQuestions');
        }
    } catch {
        status.textContent = t('errors.loadError');
    }
}

// ── Show Last Seen toggle ────────────────────────────────────────────────────

async function _loadShowLastSeen() {
    const checkbox = document.getElementById('set-privacy-show-last-seen');
    if (!checkbox) return;
    try {
        const resp = await fetch('/api/privacy/last-seen', { credentials: 'include' });
        const data = await resp.json();
        checkbox.checked = data.show_last_seen !== false;
    } catch { }
}

async function _toggleShowLastSeen(val) {
    try {
        await fetch('/api/privacy/last-seen', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ show_last_seen: val }),
        });
        window.showToast?.(val ? t('settings.lastSeenVisible') : t('settings.lastSeenHidden'), 'success');
    } catch (e) {
        window.vxAlert?.(t('errors.generic', {message: e.message}));
    }
}

// BMP toggle
async function _toggleBMP(enabled) {
    localStorage.setItem('vortex_bmp_enabled', enabled ? '1' : '0');
    if (enabled) {
        const { startBMP } = await import('../bmp-client.js');
        startBMP((roomId, ct, ts) => {
            // Deliver BMP message to chat (decrypt + display)
            console.info('[BMP] Message received for room', roomId);
        });
        window.showToast?.(t('settings.bmpEnabled'), 'success');
    } else {
        const { stopBMP } = await import('../bmp-client.js');
        stopBMP();
        window.showToast?.(t('settings.bmpDisabled'), 'info');
    }
}

function _loadBMPSetting() {
    const el = document.getElementById('set-privacy-bmp');
    if (!el) return;
    el.checked = localStorage.getItem('vortex_bmp_enabled') === '1';
}

window._toggleBMP = _toggleBMP;
window._toggleShowLastSeen = _toggleShowLastSeen;
window._showSecurityQuestionsSetup = _showSecurityQuestionsSetup;
window._saveSecurityQuestions = _saveSecurityQuestions;

// Session limit
async function _setSessionLimit(val) {
    const parsed = parseInt(val);
    const limit = (!parsed || parsed <= 0) ? 0 : Math.min(parsed, 20);
    const input = document.getElementById('session-limit-input');
    if (input) { input.value = limit || ''; input.placeholder = '\u221E'; }
    try {
        const csrf = document.cookie.match(/csrf_token=([^;]+)/)?.[1] || '';
        const resp = await fetch('/api/authentication/session-limit', {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
            body: JSON.stringify({ max_sessions: limit }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            window.showToast?.(data.error || t('settings.sessionTooNew'), 'error');
            return;
        }
        if (data.terminated > 0) {
            window.showToast?.(t('settings.terminatedOldSessions', {count: data.terminated}), 'info');
            _loadSessions();
        } else if (limit === 0) {
            window.showToast?.(t('settings.sessionLimitRemoved'), 'success');
        } else {
            window.showToast?.(t('settings.sessionLimitSet', {limit: limit}), 'success');
        }
        localStorage.setItem('vortex_session_limit', String(limit));
    } catch (e) {
        window.showToast?.(t('errors.generic', {message: e.message}), 'error');
    }
}

async function _loadSessionLimit() {
    const input = document.getElementById('session-limit-input');
    if (!input) return;
    input.placeholder = '\u221E';
    const saved = localStorage.getItem('vortex_session_limit');
    if (saved && saved !== '0') input.value = saved;
    else input.value = '';
}

window._setSessionLimit = _setSessionLimit;
window._loadSessions = _loadSessions;
window._terminateSession = _terminateSession;
window._terminateAllSessions = _terminateAllSessions;
window._setAccountTTL = _setAccountTTL;
window._showCustomTTLModal = _showCustomTTLModal;
window._saveCustomTTL = _saveCustomTTL;


// ══════════════════════════════════════════════════════════════════════════════
// Font Settings — picker, size, custom upload
// ══════════════════════════════════════════════════════════════════════════════

const _FONTS = [
    { name: 'System',           family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', builtin: true },
    { name: 'Inter',            family: '"Inter"',            url: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap' },
    { name: 'Roboto',           family: '"Roboto"',           url: 'https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap' },
    { name: 'Open Sans',        family: '"Open Sans"',        url: 'https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&display=swap' },
    { name: 'Montserrat',       family: '"Montserrat"',       url: 'https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap' },
    { name: 'Lato',             family: '"Lato"',             url: 'https://fonts.googleapis.com/css2?family=Lato:wght@400;700&display=swap' },
    { name: 'Poppins',          family: '"Poppins"',          url: 'https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap' },
    { name: 'Nunito',           family: '"Nunito"',           url: 'https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap' },
    { name: 'Raleway',          family: '"Raleway"',          url: 'https://fonts.googleapis.com/css2?family=Raleway:wght@400;600;700&display=swap' },
    { name: 'Ubuntu',           family: '"Ubuntu"',           url: 'https://fonts.googleapis.com/css2?family=Ubuntu:wght@400;500;700&display=swap' },
    { name: 'Source Sans 3',    family: '"Source Sans 3"',    url: 'https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap' },
    { name: 'Fira Sans',        family: '"Fira Sans"',        url: 'https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;700&display=swap' },
    { name: 'Noto Sans',        family: '"Noto Sans"',        url: 'https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700&display=swap' },
    { name: 'PT Sans',          family: '"PT Sans"',          url: 'https://fonts.googleapis.com/css2?family=PT+Sans:wght@400;700&display=swap' },
    { name: 'Rubik',            family: '"Rubik"',            url: 'https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;700&display=swap' },
    { name: 'Work Sans',        family: '"Work Sans"',        url: 'https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;600;700&display=swap' },
    { name: 'Manrope',          family: '"Manrope"',          url: 'https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&display=swap' },
    { name: 'DM Sans',          family: '"DM Sans"',          url: 'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap' },
    { name: 'Mulish',           family: '"Mulish"',           url: 'https://fonts.googleapis.com/css2?family=Mulish:wght@400;600;700&display=swap' },
    { name: 'Quicksand',        family: '"Quicksand"',        url: 'https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap' },
    { name: 'Josefin Sans',     family: '"Josefin Sans"',     url: 'https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@400;600;700&display=swap' },
    { name: 'Comfortaa',        family: '"Comfortaa"',        url: 'https://fonts.googleapis.com/css2?family=Comfortaa:wght@400;600;700&display=swap' },
    { name: 'IBM Plex Sans',    family: '"IBM Plex Sans"',    url: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;700&display=swap' },
    { name: 'Space Grotesk',    family: '"Space Grotesk"',    url: 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap' },
    { name: 'Exo 2',            family: '"Exo 2"',            url: 'https://fonts.googleapis.com/css2?family=Exo+2:wght@400;600;700&display=swap' },
    { name: 'Cabin',            family: '"Cabin"',            url: 'https://fonts.googleapis.com/css2?family=Cabin:wght@400;600;700&display=swap' },
    { name: 'Karla',            family: '"Karla"',            url: 'https://fonts.googleapis.com/css2?family=Karla:wght@400;600;700&display=swap' },
    { name: 'Overpass',         family: '"Overpass"',         url: 'https://fonts.googleapis.com/css2?family=Overpass:wght@400;600;700&display=swap' },
    { name: 'JetBrains Mono',   family: '"JetBrains Mono"',   url: 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap' },
    { name: 'Playfair Display', family: '"Playfair Display"', url: 'https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&display=swap' },
];

const _loadedFonts = new Set();

function _loadGoogleFont(font) {
    if (font.builtin || !font.url || _loadedFonts.has(font.name)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = font.url;
    link.dataset.vortexFont = font.name;
    document.head.appendChild(link);
    _loadedFonts.add(font.name);
}

function _renderFontPicker() {
    const grid = document.getElementById('font-picker');
    if (!grid) return;
    const current = localStorage.getItem('vortex_font') || 'System';
    grid.innerHTML = _FONTS.map(f => {
        const isActive = f.name === current;
        return `<div class="font-item${isActive ? ' active' : ''}" data-font="${f.name}"
                     onclick="window._selectFont('${f.name}')">
            <div class="font-item-name">${f.name}</div>
            <div class="font-item-preview" style="font-family:${f.family},sans-serif;">Vortex Aa</div>
        </div>`;
    }).join('');

    // Preload first few visible fonts
    _FONTS.slice(0, 9).forEach(f => _loadGoogleFont(f));

    // Lazy-load rest on scroll
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const name = entry.target.dataset.font;
                const font = _FONTS.find(f => f.name === name);
                if (font) _loadGoogleFont(font);
                observer.unobserve(entry.target);
            }
        });
    }, { root: grid, rootMargin: '100px' });
    grid.querySelectorAll('.font-item').forEach(el => observer.observe(el));
}

function _applyFontFamily(family) {
    document.documentElement.style.setProperty('--sub', family);
    document.documentElement.style.setProperty('--sans', family);
}

function _selectFont(name) {
    const font = _FONTS.find(f => f.name === name);
    const customFontFamily = localStorage.getItem('vortex_custom_font_family');
    if (name === 'custom' && customFontFamily) {
        _applyFontFamily(customFontFamily);
    } else if (font) {
        _loadGoogleFont(font);
        const family = font.builtin
            ? '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            : `${font.family}, sans-serif`;
        _applyFontFamily(family);
    }
    localStorage.setItem('vortex_font', name);
    // Update active state
    document.querySelectorAll('.font-item').forEach(el => {
        el.classList.toggle('active', el.dataset.font === name);
    });
}

function _setFontSize(px) {
    const size = parseInt(px, 10);
    document.documentElement.style.setProperty('--font-size', size + 'px');
    localStorage.setItem('vortex_font_size', size);
    const label = document.getElementById('font-size-value');
    if (label) label.textContent = size + 'px';
}

function _uploadCustomFont(input) {
    const file = input.files?.[0];
    if (!file) return;
    const name = file.name.replace(/\.(ttf|otf|woff2?|eot)$/i, '');
    const reader = new FileReader();
    reader.onload = () => {
        const dataUrl = reader.result;
        // Register font via FontFace API
        const fontFace = new FontFace(name, `url(${dataUrl})`);
        fontFace.load().then(loaded => {
            document.fonts.add(loaded);
            _applyFontFamily(`"${name}", sans-serif`);
            localStorage.setItem('vortex_font', 'custom');
            localStorage.setItem('vortex_custom_font_family', `"${name}"`);
            localStorage.setItem('vortex_custom_font_data', dataUrl);
            localStorage.setItem('vortex_custom_font_name', file.name);
            // Update UI
            const nameEl = document.getElementById('custom-font-name');
            if (nameEl) nameEl.textContent = file.name;
            document.querySelectorAll('.font-item').forEach(el => el.classList.remove('active'));
        }).catch(e => {
            console.error('Font load error:', e);
            if (typeof window.showToast === 'function') window.showToast('Failed to load font', 'error');
        });
    };
    reader.readAsDataURL(file);
    input.value = '';
}

// Restore font settings on page load
function _restoreFontSettings() {
    const fontName = localStorage.getItem('vortex_font');
    const fontSize = localStorage.getItem('vortex_font_size');
    const customData = localStorage.getItem('vortex_custom_font_data');
    const customFamily = localStorage.getItem('vortex_custom_font_family');

    if (fontSize) {
        document.documentElement.style.setProperty('--font-size', fontSize + 'px');
    }

    if (fontName === 'custom' && customData && customFamily) {
        const name = customFamily.replace(/"/g, '');
        const fontFace = new FontFace(name, `url(${customData})`);
        fontFace.load().then(loaded => {
            document.fonts.add(loaded);
            _applyFontFamily(`${customFamily}, sans-serif`);
        }).catch(() => {});
    } else if (fontName && fontName !== 'System') {
        const font = _FONTS.find(f => f.name === fontName);
        if (font) {
            _loadGoogleFont(font);
            _applyFontFamily(`${font.family}, sans-serif`);
        }
    }
}

_restoreFontSettings();

window._selectFont = _selectFont;
window._setFontSize = _setFontSize;
window._uploadCustomFont = _uploadCustomFont;
window._renderFontPicker = _renderFontPicker;

// ══════════════════════════════════════════════════════════════════════════════
// Mini App fullscreen viewer
// ══════════════════════════════════════════════════════════════════════════════

window.openMiniApp = function(botId, url, title) {
    const S      = window.AppState;
    const screen = document.getElementById('mini-app-screen');
    const body   = document.getElementById('mini-app-panel-body');
    const nameEl = document.getElementById('mini-app-panel-name');
    const subEl  = document.getElementById('mini-app-header-sub');
    if (!screen || !body) return;

    // Resolve bot info from current room when called from the chat button
    const bot    = S?.currentRoom?.dm_user;
    const name   = title || bot?.display_name || bot?.username || 'Mini App';
    const appUrl = url   || bot?.mini_app_url  || null;

    if (nameEl) nameEl.textContent = name;
    if (subEl)  subEl.textContent  = bot?.username ? '@' + bot.username : (window.t ? window.t('tabs.bots') : 'Bot').toLowerCase();

    if (appUrl) {
        body.innerHTML = `<iframe class="mini-app-iframe" src="${appUrl}"
            allow="camera; microphone; payment"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"></iframe>`;
    } else {
        body.innerHTML = `
        <div class="mini-app-placeholder">
            <div class="mini-app-placeholder-icon">
                <svg width="32" height="32" fill="#a78bfa" viewBox="0 0 24 24">
                    <path d="M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z"/>
                </svg>
            </div>
            <p class="mini-app-placeholder-title">${name}</p>
            <p class="mini-app-placeholder-sub">${window.t ? window.t('bots.noMiniAppUrl') : 'No Mini App URL configured for this bot.'}</p>
        </div>`;
    }

    screen.classList.add('mini-app-open');
    Haptic?.light?.();
};

window.closeMiniApp = function() {
    const screen = document.getElementById('mini-app-screen');
    const body   = document.getElementById('mini-app-panel-body');
    if (!screen) return;
    screen.classList.remove('mini-app-open');
    setTimeout(() => { if (body) body.innerHTML = ''; }, 350);
};


// ══════════════════════════════════════════════════════════════════════════════
// Multi-Account в настройках
// ══════════════════════════════════════════════════════════════════════════════

function _renderSettingsAccounts() {
    const container = document.getElementById('settings-accounts-section');
    if (!container) return;

    const { getAccounts } = window;
    if (!getAccounts) return;

    const accounts = getAccounts();
    const currentId = window.AppState?.user?.user_id;

    if (accounts.length <= 1) {
        // Одиночный аккаунт — показываем только кнопку добавления
        container.innerHTML = `
            <div class="set-ma-add" onclick="window.addNewAccount?.()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/>
                    <line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/>
                </svg>
                <span>${t('auth.addAccount')}</span>
            </div>
        `;
        return;
    }

    let html = '';
    for (const acc of accounts) {
        const isCurrent = acc.user_id === currentId;
        const avatar = acc.avatar_url
            ? `<img src="${acc.avatar_url}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`
            : (acc.avatar_emoji || '👤');

        html += `
        <div class="set-ma-card${isCurrent ? ' set-ma-active' : ''}"
             ${isCurrent ? '' : `onclick="window.switchAccount?.(${acc.user_id})"`}>
            <div class="set-ma-avatar">${avatar}</div>
            <div class="set-ma-info">
                <div class="set-ma-name">${acc.display_name || acc.username}</div>
                <div class="set-ma-uname">@${acc.username}</div>
            </div>
            ${isCurrent
                ? '<svg class="set-ma-check" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
                : `<button class="set-ma-remove" onclick="event.stopPropagation();window.removeAccount?.(${acc.user_id});_renderSettingsAccounts();" title="${t('settings.remove')}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                   </button>`
            }
        </div>`;
    }

    if (accounts.length < 4) {
        html += `
        <div class="set-ma-add" onclick="window.addNewAccount?.()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/>
                <line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/>
            </svg>
            <span>${t('auth.addAccount')}</span>
        </div>`;
    }

    container.innerHTML = html;
}

