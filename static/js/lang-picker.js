/**
 * First-launch language picker.
 * Shows once when vortex_locale is not set in localStorage.
 * After selection, saves locale and reveals the auth screen.
 */

const _LP_LANGS = [
    {code:"ru",name:"Русский",hint:"Выберите язык"},
    {code:"en",name:"English",hint:"Choose your language"},
    {code:"uk",name:"Українська",hint:"Оберіть мову"},
    {code:"es",name:"Español",hint:"Elige tu idioma"},
    {code:"fr",name:"Français",hint:"Choisissez votre langue"},
    {code:"de",name:"Deutsch",hint:"Wähle deine Sprache"},
    {code:"it",name:"Italiano",hint:"Scegli la tua lingua"},
    {code:"pt",name:"Português",hint:"Escolha seu idioma"},
    {code:"zh",name:"中文",hint:"选择语言"},
    {code:"ja",name:"日本語",hint:"言語を選択"},
    {code:"ko",name:"한국어",hint:"언어를 선택하세요"},
    {code:"ar",name:"العربية",hint:"اختر لغتك"},
    {code:"hi",name:"हिन्दी",hint:"अपनी भाषा चुनें"},
    {code:"tr",name:"Türkçe",hint:"Dilinizi seçin"},
    {code:"pl",name:"Polski",hint:"Wybierz język"},
    {code:"nl",name:"Nederlands",hint:"Kies je taal"},
    {code:"th",name:"ไทย",hint:"เลือกภาษา"},
    {code:"vi",name:"Tiếng Việt",hint:"Chọn ngôn ngữ"},
    {code:"id",name:"Bahasa Indonesia",hint:"Pilih bahasa"},
    {code:"cs",name:"Čeština",hint:"Vyberte jazyk"},
    {code:"sv",name:"Svenska",hint:"Välj språk"},
    {code:"ro",name:"Română",hint:"Alege limba"},
    {code:"hu",name:"Magyar",hint:"Válaszd ki a nyelvet"},
    {code:"el",name:"Ελληνικά",hint:"Επιλέξτε γλώσσα"},
    {code:"da",name:"Dansk",hint:"Vælg sprog"},
    {code:"fi",name:"Suomi",hint:"Valitse kieli"},
    {code:"no",name:"Norsk",hint:"Velg språk"},
    {code:"he",name:"עברית",hint:"בחר שפה"},
    {code:"fa",name:"فارسی",hint:"زبان خود را انتخاب کنید"},
    {code:"bg",name:"Български",hint:"Изберете език"},
    {code:"hr",name:"Hrvatski",hint:"Odaberite jezik"},
    {code:"sr",name:"Српски",hint:"Изаберите језик"},
    {code:"sk",name:"Slovenčina",hint:"Vyberte jazyk"},
    {code:"sl",name:"Slovenščina",hint:"Izberite jezik"},
    {code:"lt",name:"Lietuvių",hint:"Pasirinkite kalbą"},
    {code:"lv",name:"Latviešu",hint:"Izvēlieties valodu"},
    {code:"et",name:"Eesti",hint:"Vali keel"},
    {code:"ka",name:"ქართული",hint:"აირჩიეთ ენა"},
    {code:"hy",name:"Հայերեն",hint:"Ընտրեք լdelays"},
    {code:"az",name:"Azərbaycan",hint:"Dili seçin"},
    {code:"kk",name:"Қазақша",hint:"Тілді таңдаңыз"},
    {code:"uz",name:"Oʻzbek",hint:"Tilni tanlang"},
    {code:"bn",name:"বাংলা",hint:"ভাষা নির্বাচন করুন"},
    {code:"ms",name:"Bahasa Melayu",hint:"Pilih bahasa"},
    {code:"af",name:"Afrikaans",hint:"Kies jou taal"},
    {code:"sw",name:"Kiswahili",hint:"Chagua lugha"},
    {code:"ca",name:"Català",hint:"Tria el teu idioma"},
    {code:"eu",name:"Euskara",hint:"Aukeratu hizkuntza"},
    {code:"gl",name:"Galego",hint:"Elixe o teu idioma"},
    {code:"is",name:"Íslenska",hint:"Veldu tungumál"},
    {code:"mk",name:"Македонски",hint:"Изберете јазик"},
    {code:"be",name:"Беларуская",hint:"Абярыце мову"},
    {code:"mn",name:"Монгол",hint:"Хэлээ сонго"},
    {code:"ky",name:"Кыргызча",hint:"Тилди тандаңыз"},
    {code:"ur",name:"اردو",hint:"اپنی زبان منتخب کریں"},
    {code:"ta",name:"தமிழ்",hint:"மொழியைத் தேர்வுசெய்"},
    {code:"te",name:"తెలుగు",hint:"భాషను ఎంచుకోండి"},
    {code:"mr",name:"मराठी",hint:"भाषा निवडा"},
    {code:"gu",name:"ગુજરાતી",hint:"ભાષા પસંદ કરો"},
    {code:"kn",name:"ಕನ್ನಡ",hint:"ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ"},
    {code:"ml",name:"മലയാളം",hint:"ഭാഷ തിരഞ്ഞെടുക്കുക"},
    {code:"pa",name:"ਪੰਜਾਬੀ",hint:"ਭਾਸ਼ਾ ਚੁਣੋ"},
    {code:"ne",name:"नेपाली",hint:"भाषा छान्नुहोस्"},
    {code:"si",name:"සිංහල",hint:"භාෂාව තෝරන්න"},
    {code:"km",name:"ភាសាខ្មែរ",hint:"ជ្រើសរើសភាសា"},
    {code:"my",name:"မြန်မာ",hint:"ဘာသာစကားရွေးပါ"},
    {code:"zh-TW",name:"繁體中文",hint:"選擇語言"},
    {code:"tl",name:"Filipino",hint:"Pumili ng wika"},
    {code:"zu",name:"isiZulu",hint:"Khetha ulimi"},
    {code:"eo",name:"Esperanto",hint:"Elektu lingvon"},
    {code:"ga",name:"Gaeilge",hint:"Roghnaigh teanga"},
    {code:"cy",name:"Cymraeg",hint:"Dewiswch iaith"},
    {code:"so",name:"Soomaali",hint:"Dooro luuqadda"},
    {code:"ku",name:"Kurdî",hint:"Zimanê xwe hilbijêre"},
    {code:"am",name:"አማርኛ",hint:"ቋንቋ ይምረጡ"},
    {code:"ha",name:"Hausa",hint:"Zaɓi harshe"},
    {code:"sq",name:"Shqip",hint:"Zgjidhni gjuhën"},
    {code:"bs",name:"Bosanski",hint:"Odaberite jezik"},
    {code:"tg",name:"Тоҷикӣ",hint:"Забонро интихоб кунед"},
    {code:"tk",name:"Türkmen",hint:"Dili saýlaň"},
    {code:"ti",name:"ትግርኛ",hint:"ቋንቋ ምረጹ"},
    {code:"yi",name:"ייִדיש",hint:"קלייַבט אויס שפּראַך"},
    {code:"ny",name:"Chichewa",hint:"Sankhani chilankhulo"},
    {code:"st",name:"Sesotho",hint:"Khetha puo"},
    {code:"gd",name:"Gàidhlig",hint:"Tagh cànan"},
    {code:"fy",name:"Frysk",hint:"Kies jo taal"},
    {code:"co",name:"Corsu",hint:"Sceglie a lingua"},
    {code:"sm",name:"Gagana Sāmoa",hint:"Filifili gagana"},
    {code:"ay",name:"Aymar aru",hint:"Arunt'aña"},
    {code:"ee",name:"Eʋegbe",hint:"Tia gbe"},
    {code:"ak",name:"Akan",hint:"Yi kasa"},
    {code:"bho",name:"भोजपुरी",hint:"भाषा चुनीं"},
    {code:"doi",name:"डोगरी",hint:"बोली चुनो"},
    {code:"dv",name:"ދިވެހި",hint:"ބަސް ޚިޔާރުކުރައްވާ"},
    {code:"hmn",name:"Hmong",hint:"Xaiv lus"},
    {code:"ilo",name:"Ilokano",hint:"Pilien ti pagsasao"},
    {code:"kri",name:"Krio",hint:"Pik langwej"},
    {code:"lus",name:"Mizo ṭawng",hint:"Ṭawng thlang rawh"},
    {code:"nso",name:"Sepedi",hint:"Kgetha polelo"},
    {code:"ckb",name:"کوردیی ناوەندی",hint:"زمان هەڵبژێرە"},
];

let _lpSelected = null;

// ── Typewriter title rotation ───────────────────────────────────────────
// Hints in order: popular languages first, less common last
const _TITLE_HINTS = _LP_LANGS.map(l => l.hint).filter(Boolean);

let _titleIdx = 0;
let _titleRafId = null;
let _titleRunning = false;

const _TYPE_SPEED   = 45;   // ms per character typing
const _DELETE_SPEED  = 30;   // ms per character deleting
const _PAUSE_AFTER   = 1800; // ms to hold completed text

function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function _typewriterLoop() {
    const el = document.getElementById('lp-title');
    if (!el) return;
    _titleRunning = true;

    while (_titleRunning) {
        const text = _TITLE_HINTS[_titleIdx];

        // Type in
        for (let i = 0; i <= text.length && _titleRunning; i++) {
            el.textContent = text.slice(0, i);
            await _sleep(_TYPE_SPEED);
        }

        if (!_titleRunning) break;
        await _sleep(_PAUSE_AFTER);
        if (!_titleRunning) break;

        // Delete
        const current = el.textContent;
        for (let i = current.length; i >= 0 && _titleRunning; i--) {
            el.textContent = current.slice(0, i);
            await _sleep(_DELETE_SPEED);
        }

        if (!_titleRunning) break;
        await _sleep(200);

        _titleIdx = (_titleIdx + 1) % _TITLE_HINTS.length;
    }
}

function _startTitleRotation() {
    _titleRunning = true;
    _typewriterLoop();
}

function _stopTitleRotation() {
    _titleRunning = false;
}

// ── Render language list (safe DOM construction) ────────────────────────

function _createLpItem(lang) {
    const div = document.createElement('div');
    div.className = 'lp-item' + (_lpSelected === lang.code ? ' selected' : '');
    div.dataset.code = lang.code;
    div.onclick = () => window._lpSelect(lang.code);

    const radio = document.createElement('div');
    radio.className = 'lp-item-radio';

    const name = document.createElement('span');
    name.className = 'lp-item-name';
    name.textContent = lang.name;

    const code = document.createElement('span');
    code.className = 'lp-item-code';
    code.textContent = lang.code;

    div.append(radio, name, code);
    return div;
}

function _renderLpList(query) {
    const list = document.getElementById('lp-list');
    if (!list) return;
    const q = (query || '').toLowerCase();
    const filtered = q
        ? _LP_LANGS.filter(l => l.name.toLowerCase().includes(q) || l.code.includes(q))
        : _LP_LANGS;

    list.replaceChildren(...filtered.map(_createLpItem));
}

// ── Select language ─────────────────────────────────────────────────────

let _selectVersion = 0; // cancel previous typewriter on re-select

window._lpSelect = function(code) {
    _lpSelected = code;
    _renderLpList(document.getElementById('lp-search')?.value || '');

    // Update button
    const btn = document.getElementById('lp-continue');
    if (btn) btn.disabled = false;

    // Update title to selected language's hint with typewriter
    const lang = _LP_LANGS.find(l => l.code === code);
    if (lang) {
        _stopTitleRotation();
        const el = document.getElementById('lp-title');
        if (el) {
            const ver = ++_selectVersion;
            const oldText = el.textContent;
            (async () => {
                // Delete old text
                for (let i = oldText.length; i >= 0; i--) {
                    if (_selectVersion !== ver) return;
                    el.textContent = oldText.slice(0, i);
                    await _sleep(_DELETE_SPEED);
                }
                if (_selectVersion !== ver) return;
                await _sleep(150);
                // Type new text
                const newText = lang.hint;
                for (let i = 0; i <= newText.length; i++) {
                    if (_selectVersion !== ver) return;
                    el.textContent = newText.slice(0, i);
                    await _sleep(_TYPE_SPEED);
                }
            })();
        }
        // Update button text
        const CONTINUE_MAP = {
            ru:"Продолжить",en:"Continue",uk:"Продовжити",es:"Continuar",fr:"Continuer",
            de:"Weiter",it:"Continua",pt:"Continuar",zh:"继续","zh-TW":"繼續",ja:"続ける",
            ko:"계속",ar:"متابعة",hi:"जारी रखें",tr:"Devam",pl:"Kontynuuj",nl:"Doorgaan",
            th:"ดำเนินการต่อ",vi:"Tiếp tục",id:"Lanjutkan",cs:"Pokračovat",sv:"Fortsätt",
            ro:"Continuă",hu:"Folytatás",el:"Συνέχεια",da:"Fortsæt",fi:"Jatka",
            no:"Fortsett",he:"המשך",fa:"ادامه",bg:"Продължи",hr:"Nastavi",
            sr:"Настави",sk:"Pokračovať",sl:"Nadaljuj",lt:"Tęsti",lv:"Turpināt",
            et:"Jätka",ka:"გაგრძელება",hy:"Շարունակել",az:"Davam",kk:"Жалғастыру",
            uz:"Davom",bn:"চালিয়ে যান",ms:"Teruskan",
        };
        const btnText = document.getElementById('lp-continue-text');
        if (btnText) btnText.textContent = CONTINUE_MAP[code] || 'Continue';

        // Update subtitle
        const SUB_MAP = {
            ru:"Можно изменить позже в настройках",en:"You can change it later in settings",
            uk:"Можна змінити пізніше в налаштуваннях",es:"Puedes cambiarlo en ajustes",
            fr:"Modifiable dans les paramètres",de:"Kann in Einstellungen geändert werden",
            it:"Puoi cambiarlo nelle impostazioni",pt:"Pode alterar nas configurações",
            zh:"可以在设置中更改",ja:"設定で変更できます",ko:"설정에서 변경 가능",
            tr:"Ayarlardan değiştirebilirsiniz",pl:"Zmienisz w ustawieniach",
            ar:"يمكنك تغييرها في الإعدادات",hi:"सेटिंग्स में बदल सकते हैं",
        };
        const sub = document.getElementById('lp-subtitle');
        if (sub) sub.textContent = SUB_MAP[code] || SUB_MAP.en;
    }

    // Scroll selected into view
    setTimeout(() => {
        const selected = document.querySelector('.lp-item.selected');
        if (selected) selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }, 50);
};

window._lpFilter = function(q) {
    _renderLpList(q);
};

// ── Confirm selection ───────────────────────────────────────────────────

window._lpConfirm = async function() {
    if (!_lpSelected) return;

    // Save locale
    localStorage.setItem('vortex_locale', _lpSelected);

    // Apply locale if setLocale is available
    if (window.setLocale) {
        await window.setLocale(_lpSelected);
    }

    // Animate out
    const screen = document.getElementById('lang-picker-screen');
    if (screen) {
        screen.style.transition = 'opacity 0.4s ease-out';
        screen.style.opacity = '0';
        setTimeout(() => {
            screen.style.display = 'none';
        }, 400);
    }

    _stopTitleRotation();
};

// ── Init: check if should show ──────────────────────────────────────────

export function initLangPicker() {
    const saved = localStorage.getItem('vortex_locale');
    if (saved) return; // Language already chosen

    const screen = document.getElementById('lang-picker-screen');
    if (!screen) return;

    // Hide auth screen while picker is visible
    const auth = document.getElementById('auth-screen');
    if (auth) auth.style.display = 'none';

    screen.style.display = 'flex';
    _renderLpList();
    _startTitleRotation();

    // Ничего не предвыбираем — пользователь сам выбирает язык

    // When picker closes, show auth
    const observer = new MutationObserver(() => {
        if (screen.style.display === 'none') {
            if (auth) auth.style.display = 'flex';
            observer.disconnect();
        }
    });
    observer.observe(screen, { attributes: true, attributeFilter: ['style'] });
}
