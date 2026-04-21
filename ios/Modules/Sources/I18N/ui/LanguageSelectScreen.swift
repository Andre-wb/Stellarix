import SwiftUI

/// First-run language chooser. Matches the web client's `lang-picker`
/// screen: orb background, gradient logo tile, typewriter-animated
/// multilingual title, rounded list with purple-radio selection,
/// gradient Continue button. Fills the whole screen on phone — no
/// fixed card width.
public struct LocaleOption: Sendable, Hashable, Identifiable {
    public let code: String          // "ru", "en", "zh-TW" …
    public let nativeName: String    // "Русский", "中文" …
    public let hint: String          // "Выберите язык", "Choose your language" …
    public var id: String { code }
    public init(code: String, nativeName: String, hint: String) {
        self.code = code; self.nativeName = nativeName; self.hint = hint
    }
}

public enum LanguageCatalog {
    /// Same slugs + hints as `static/js/lang-picker.js` so the
    /// typewriter cycles through the exact same 97 phrases.
    public static let all: [LocaleOption] = [
        .init(code: "ru",    nativeName: "Русский",         hint: "Выберите язык"),
        .init(code: "en",    nativeName: "English",         hint: "Choose your language"),
        .init(code: "uk",    nativeName: "Українська",      hint: "Оберіть мову"),
        .init(code: "es",    nativeName: "Español",         hint: "Elige tu idioma"),
        .init(code: "fr",    nativeName: "Français",        hint: "Choisissez votre langue"),
        .init(code: "de",    nativeName: "Deutsch",         hint: "Wähle deine Sprache"),
        .init(code: "it",    nativeName: "Italiano",        hint: "Scegli la tua lingua"),
        .init(code: "pt",    nativeName: "Português",       hint: "Escolha seu idioma"),
        .init(code: "zh",    nativeName: "中文",             hint: "选择语言"),
        .init(code: "ja",    nativeName: "日本語",           hint: "言語を選択"),
        .init(code: "ko",    nativeName: "한국어",           hint: "언어를 선택하세요"),
        .init(code: "ar",    nativeName: "العربية",         hint: "اختر لغتك"),
        .init(code: "hi",    nativeName: "हिन्दी",          hint: "अपनी भाषा चुनें"),
        .init(code: "tr",    nativeName: "Türkçe",          hint: "Dilinizi seçin"),
        .init(code: "pl",    nativeName: "Polski",          hint: "Wybierz język"),
        .init(code: "nl",    nativeName: "Nederlands",      hint: "Kies je taal"),
        .init(code: "th",    nativeName: "ไทย",              hint: "เลือกภาษา"),
        .init(code: "vi",    nativeName: "Tiếng Việt",       hint: "Chọn ngôn ngữ"),
        .init(code: "id",    nativeName: "Bahasa Indonesia", hint: "Pilih bahasa"),
        .init(code: "cs",    nativeName: "Čeština",          hint: "Vyberte jazyk"),
        .init(code: "sv",    nativeName: "Svenska",          hint: "Välj språk"),
        .init(code: "ro",    nativeName: "Română",           hint: "Alege limba"),
        .init(code: "hu",    nativeName: "Magyar",           hint: "Válaszd ki a nyelvet"),
        .init(code: "el",    nativeName: "Ελληνικά",         hint: "Επιλέξτε γλώσσα"),
        .init(code: "da",    nativeName: "Dansk",            hint: "Vælg sprog"),
        .init(code: "fi",    nativeName: "Suomi",            hint: "Valitse kieli"),
        .init(code: "no",    nativeName: "Norsk",            hint: "Velg språk"),
        .init(code: "he",    nativeName: "עברית",            hint: "בחר שפה"),
        .init(code: "fa",    nativeName: "فارسی",            hint: "زبان خود را انتخاب کنید"),
        .init(code: "bg",    nativeName: "Български",        hint: "Изберете език"),
        .init(code: "hr",    nativeName: "Hrvatski",         hint: "Odaberite jezik"),
        .init(code: "sr",    nativeName: "Српски",           hint: "Изаберите језик"),
        .init(code: "sk",    nativeName: "Slovenčina",       hint: "Vyberte jazyk"),
        .init(code: "sl",    nativeName: "Slovenščina",      hint: "Izberite jezik"),
        .init(code: "lt",    nativeName: "Lietuvių",         hint: "Pasirinkite kalbą"),
        .init(code: "lv",    nativeName: "Latviešu",         hint: "Izvēlieties valodu"),
        .init(code: "et",    nativeName: "Eesti",            hint: "Vali keel"),
        .init(code: "ka",    nativeName: "ქართული",         hint: "აირჩიეთ ენა"),
        .init(code: "hy",    nativeName: "Հայերեն",          hint: "Ընտրեք լեզուն"),
        .init(code: "az",    nativeName: "Azərbaycan",       hint: "Dili seçin"),
        .init(code: "kk",    nativeName: "Қазақша",          hint: "Тілді таңдаңыз"),
        .init(code: "uz",    nativeName: "Oʻzbek",           hint: "Tilni tanlang"),
        .init(code: "bn",    nativeName: "বাংলা",            hint: "ভাষা নির্বাচন করুন"),
        .init(code: "ms",    nativeName: "Bahasa Melayu",    hint: "Pilih bahasa"),
        .init(code: "af",    nativeName: "Afrikaans",        hint: "Kies jou taal"),
        .init(code: "sw",    nativeName: "Kiswahili",        hint: "Chagua lugha"),
        .init(code: "ca",    nativeName: "Català",           hint: "Tria el teu idioma"),
        .init(code: "eu",    nativeName: "Euskara",          hint: "Aukeratu hizkuntza"),
        .init(code: "gl",    nativeName: "Galego",           hint: "Elixe o teu idioma"),
        .init(code: "is",    nativeName: "Íslenska",         hint: "Veldu tungumál"),
        .init(code: "mk",    nativeName: "Македонски",       hint: "Изберете јазик"),
        .init(code: "be",    nativeName: "Беларуская",       hint: "Абярыце мову"),
        .init(code: "mn",    nativeName: "Монгол",           hint: "Хэлээ сонго"),
        .init(code: "ky",    nativeName: "Кыргызча",         hint: "Тилди тандаңыз"),
        .init(code: "ur",    nativeName: "اردو",             hint: "اپنی زبان منتخب کریں"),
        .init(code: "ta",    nativeName: "தமிழ்",           hint: "மொழியைத் தேர்வுசெய்"),
        .init(code: "te",    nativeName: "తెలుగు",          hint: "భాషను ఎంచుకోండి"),
        .init(code: "mr",    nativeName: "मराठी",            hint: "भाषा निवडा"),
        .init(code: "gu",    nativeName: "ગુજરાતી",           hint: "ભાષા પસંદ કરો"),
        .init(code: "kn",    nativeName: "ಕನ್ನಡ",            hint: "ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ"),
        .init(code: "ml",    nativeName: "മലയാളം",           hint: "ഭാഷ തിരഞ്ഞെടുക്കുക"),
        .init(code: "pa",    nativeName: "ਪੰਜਾਬੀ",           hint: "ਭਾਸ਼ਾ ਚੁਣੋ"),
        .init(code: "ne",    nativeName: "नेपाली",           hint: "भाषा छान्नुहोस्"),
        .init(code: "si",    nativeName: "සිංහල",             hint: "භාෂාව තෝරන්න"),
        .init(code: "km",    nativeName: "ភាសាខ្មែរ",         hint: "ជ្រើសរើសភាសា"),
        .init(code: "my",    nativeName: "မြန်မာ",            hint: "ဘာသာစကားရွေးပါ"),
        .init(code: "zh-TW", nativeName: "繁體中文",          hint: "選擇語言"),
        .init(code: "tl",    nativeName: "Filipino",         hint: "Pumili ng wika"),
        .init(code: "zu",    nativeName: "isiZulu",          hint: "Khetha ulimi"),
        .init(code: "eo",    nativeName: "Esperanto",        hint: "Elektu lingvon"),
        .init(code: "ga",    nativeName: "Gaeilge",          hint: "Roghnaigh teanga"),
        .init(code: "cy",    nativeName: "Cymraeg",          hint: "Dewiswch iaith"),
        .init(code: "so",    nativeName: "Soomaali",         hint: "Dooro luuqadda"),
        .init(code: "ku",    nativeName: "Kurdî",            hint: "Zimanê xwe hilbijêre"),
        .init(code: "am",    nativeName: "አማርኛ",             hint: "ቋንቋ ይምረጡ"),
        .init(code: "ha",    nativeName: "Hausa",            hint: "Zaɓi harshe"),
        .init(code: "sq",    nativeName: "Shqip",            hint: "Zgjidhni gjuhën"),
        .init(code: "bs",    nativeName: "Bosanski",         hint: "Odaberite jezik"),
        .init(code: "tg",    nativeName: "Тоҷикӣ",           hint: "Забонро интихоб кунед"),
        .init(code: "tk",    nativeName: "Türkmen",          hint: "Dili saýlaň"),
        .init(code: "ti",    nativeName: "ትግርኛ",             hint: "ቋንቋ ምረጹ"),
        .init(code: "yi",    nativeName: "ייִדיש",            hint: "קלייַבט אויס שפּראַך"),
        .init(code: "ny",    nativeName: "Chichewa",         hint: "Sankhani chilankhulo"),
        .init(code: "st",    nativeName: "Sesotho",          hint: "Khetha puo"),
        .init(code: "gd",    nativeName: "Gàidhlig",         hint: "Tagh cànan"),
        .init(code: "fy",    nativeName: "Frysk",            hint: "Kies jo taal"),
        .init(code: "co",    nativeName: "Corsu",            hint: "Sceglie a lingua"),
        .init(code: "sm",    nativeName: "Gagana Sāmoa",     hint: "Filifili gagana"),
        .init(code: "ay",    nativeName: "Aymar aru",        hint: "Arunt'aña"),
        .init(code: "ee",    nativeName: "Eʋegbe",           hint: "Tia gbe"),
        .init(code: "ak",    nativeName: "Akan",             hint: "Yi kasa"),
        .init(code: "bho",   nativeName: "भोजपुरी",           hint: "भाषा चुनीं"),
        .init(code: "doi",   nativeName: "डोगरी",            hint: "बोली चुनो"),
        .init(code: "dv",    nativeName: "ދިވެހި",            hint: "ބަސް ޚިޔާރުކުރައްވާ"),
        .init(code: "hmn",   nativeName: "Hmong",            hint: "Xaiv lus"),
        .init(code: "ilo",   nativeName: "Ilokano",          hint: "Pilien ti pagsasao"),
        .init(code: "kri",   nativeName: "Krio",             hint: "Pik langwej"),
        .init(code: "lus",   nativeName: "Mizo ṭawng",       hint: "Ṭawng thlang rawh"),
        .init(code: "nso",   nativeName: "Sepedi",           hint: "Kgetha polelo"),
        .init(code: "ckb",   nativeName: "کوردیی ناوەندی",   hint: "زمان هەڵبژێرە"),
    ]
}

/// Web-side palette tokens — `static/css/variables.css` one-to-one.
public enum VortexPalette {
    public static let bg         = Color(red: 0x09/255, green: 0x09/255, blue: 0x0B/255)
    public static let bg2        = Color(red: 0x11/255, green: 0x11/255, blue: 0x15/255)
    public static let bg3        = Color(red: 0x18/255, green: 0x18/255, blue: 0x1D/255)
    public static let border     = Color(red: 0x20/255, green: 0x20/255, blue: 0x27/255)
    public static let accent     = Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255)
    public static let accent2    = Color(red: 0xA8/255, green: 0x55/255, blue: 0xF7/255)
    public static let accentDark = Color(red: 0x6D/255, green: 0x28/255, blue: 0xD9/255)
    public static let teal       = Color(red: 0x4E/255, green: 0xCD/255, blue: 0xC4/255)
    public static let cyan       = Color(red: 0x06/255, green: 0xB6/255, blue: 0xD4/255)
    public static let text       = Color(red: 0xE4/255, green: 0xE4/255, blue: 0xE7/255)
    public static let text2      = Color(red: 0x71/255, green: 0x71/255, blue: 0x7A/255)
    public static let text3      = Color(red: 0x52/255, green: 0x52/255, blue: 0x5B/255)
    public static let red        = Color(red: 0xEF/255, green: 0x44/255, blue: 0x44/255)
    public static let green      = Color(red: 0x22/255, green: 0xC5/255, blue: 0x5E/255)
}

/// Drives the typewriter: types `hint[i]` character-by-character,
/// pauses, deletes, advances to the next. Published state is read by
/// the title view. Runs on @MainActor so text updates don't race.
@MainActor
final class TypewriterModel: ObservableObject {
    @Published var displayed: String = ""
    private var idx = 0
    private var running = false
    private let hints: [String]

    init(hints: [String]) {
        self.hints = hints.filter { !$0.isEmpty }
    }

    func start() {
        guard !running, !hints.isEmpty else { return }
        running = true
        Task { await loop() }
    }

    func stop() { running = false }

    private func loop() async {
        while running {
            let text = hints[idx]
            // type in
            for i in 0...text.count {
                if !running { return }
                displayed = String(text.prefix(i))
                try? await Task.sleep(nanoseconds: 45_000_000)
            }
            if !running { return }
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            if !running { return }
            // delete
            let current = displayed
            for i in stride(from: current.count, through: 0, by: -1) {
                if !running { return }
                displayed = String(current.prefix(i))
                try? await Task.sleep(nanoseconds: 30_000_000)
            }
            if !running { return }
            try? await Task.sleep(nanoseconds: 200_000_000)
            idx = (idx + 1) % hints.count
        }
    }
}

public struct LanguageSelectScreen: View {
    @State private var picked: String
    @State private var query: String = ""
    @State private var cursorOn: Bool = true
    @StateObject private var typewriter: TypewriterModel
    private let locales: LocaleSource
    private let onContinue: (String) -> Void

    public init(locales: LocaleSource, preselected: String = "en",
                onContinue: @escaping (String) -> Void) {
        self.locales = locales
        self.onContinue = onContinue
        self._picked = State(initialValue: preselected)
        self._typewriter = StateObject(wrappedValue: TypewriterModel(
            hints: LanguageCatalog.all.map(\.hint),
        ))
    }

    private var filtered: [LocaleOption] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return LanguageCatalog.all }
        return LanguageCatalog.all.filter {
            $0.nativeName.lowercased().contains(q) || $0.code.lowercased().contains(q)
        }
    }

    public var body: some View {
        ZStack {
            Color(red: 0x07/255, green: 0x06/255, blue: 0x0E/255).ignoresSafeArea()
            LangOrbs()
            content
        }
        .preferredColorScheme(.dark)
        .onAppear {
            typewriter.start()
            Timer.scheduledTimer(withTimeInterval: 0.6, repeats: true) { _ in
                DispatchQueue.main.async { cursorOn.toggle() }
            }
        }
        .onDisappear { typewriter.stop() }
    }

    private var content: some View {
        VStack(spacing: 14) {
            VStack(spacing: 10) {
                LogoTile()
                Text("VORTEX")
                    .font(.system(size: 30, weight: .black))
                    .tracking(6)
                    .foregroundStyle(.white)
            }
            .padding(.top, 20)
            // Typewriter title — cycles through "Выберите язык" /
            // "Choose your language" / … with a blinking caret.
            HStack(spacing: 1) {
                Text(typewriter.displayed)
                    .font(.system(size: 18, weight: .heavy))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Text("|")
                    .font(.system(size: 18, weight: .light))
                    .foregroundStyle(VortexPalette.accent.opacity(0.8))
                    .opacity(cursorOn ? 1 : 0)
            }
            .frame(maxWidth: .infinity, minHeight: 24, alignment: .center)
            .padding(.horizontal, 20)

            Text("You can change it later in settings")
                .font(.system(size: 12))
                .foregroundStyle(.white.opacity(0.4))

            // Search
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.white.opacity(0.35))
                TextField("",
                          text: $query,
                          prompt: Text("Search / Поиск / Buscar…")
                              .foregroundColor(.white.opacity(0.28)))
                    .textFieldStyle(.plain)
                    .foregroundStyle(.white)
                    .font(.system(size: 14))
                    #if canImport(UIKit)
                    .textInputAutocapitalization(.never)
                    #endif
                    .autocorrectionDisabled()
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.white.opacity(0.06))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.white.opacity(0.08), lineWidth: 1),
                    ),
            )
            .padding(.horizontal, 16)

            // List — expands to fill remaining space
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(filtered) { l in
                        LangRow(option: l, selected: l.code == picked)
                            .onTapGesture { picked = l.code }
                        Divider().background(Color.white.opacity(0.04))
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.white.opacity(0.03))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.white.opacity(0.06), lineWidth: 1),
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal, 16)

            HStack(spacing: 10) {
                Button { commit() } label: {
                    Text("Skip to chat")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(.white.opacity(0.7))
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(VortexPalette.bg3)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(VortexPalette.border, lineWidth: 1),
                                ),
                        )
                }
                .buttonStyle(.plain)

                Button { commit() } label: {
                    HStack(spacing: 6) {
                        Text("Continue")
                            .font(.system(size: 16, weight: .heavy))
                        Image(systemName: "arrow.right")
                            .font(.system(size: 14, weight: .bold))
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(
                        LinearGradient(
                            colors: [VortexPalette.accent, VortexPalette.accentDark],
                            startPoint: .topLeading, endPoint: .bottomTrailing,
                        ),
                        in: RoundedRectangle(cornerRadius: 12),
                    )
                    .shadow(color: VortexPalette.accent.opacity(0.4),
                            radius: 18, x: 0, y: 4)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func commit() {
        UserDefaults.standard.set(picked, forKey: "locale")
        UserDefaults.standard.set(true, forKey: "vortex.language.picked")
        Task { await locales.setLocale(picked) }
        onContinue(picked)
    }
}

// MARK: - Sub-views -------------------------------------------------

private struct LogoTile: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 14)
            .fill(
                LinearGradient(
                    colors: [VortexPalette.accent, VortexPalette.teal],
                    startPoint: .topLeading, endPoint: .bottomTrailing,
                ),
            )
            .frame(width: 56, height: 56)
            .overlay(
                Image(systemName: "globe")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(.white),
            )
            .shadow(color: VortexPalette.accent.opacity(0.4),
                    radius: 24, x: 0, y: 4)
    }
}

private struct LangRow: View {
    let option: LocaleOption
    let selected: Bool
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .stroke(selected ? VortexPalette.accent : Color.white.opacity(0.2),
                            lineWidth: 2)
                    .frame(width: 22, height: 22)
                if selected {
                    Circle()
                        .fill(VortexPalette.accent)
                        .frame(width: 22, height: 22)
                    Circle()
                        .fill(.white)
                        .frame(width: 8, height: 8)
                }
            }
            Text(option.nativeName)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(.white)
                .lineLimit(1)
            Spacer()
            Text(option.code.uppercased())
                .font(.system(size: 11, design: .monospaced))
                .tracking(1)
                .foregroundStyle(.white.opacity(0.3))
        }
        .padding(.horizontal, 16).padding(.vertical, 14)
        .background(selected ? VortexPalette.accent.opacity(0.12) : .clear)
        .contentShape(Rectangle())
    }
}

private struct LangOrbs: View {
    var body: some View {
        GeometryReader { geo in
            ZStack {
                orb(color: VortexPalette.accent,
                    x: geo.size.width * 0.0,  y: geo.size.height * 0.0,  size: 420)
                orb(color: VortexPalette.cyan,
                    x: geo.size.width * 1.0,  y: geo.size.height * 1.0,  size: 380)
                orb(color: VortexPalette.teal,
                    x: geo.size.width * 0.5,  y: geo.size.height * 0.5,  size: 320)
            }
        }
        .ignoresSafeArea()
        .opacity(0.35)
    }
    private func orb(color: Color, x: CGFloat, y: CGFloat, size: CGFloat) -> some View {
        Circle()
            .fill(
                RadialGradient(
                    colors: [color, .clear],
                    center: .center, startRadius: 0, endRadius: size / 2,
                ),
            )
            .frame(width: size, height: size)
            .blur(radius: 70)
            .position(x: x, y: y)
    }
}

public struct VortexLogo: View {
    public init() {}
    public var body: some View {
        VStack(spacing: 12) {
            LogoTile()
            Text("VORTEX")
                .font(.system(size: 28, weight: .black))
                .tracking(6)
                .foregroundStyle(.white)
        }
    }
}
