import SwiftUI
import PhotosUI
import I18N
#if canImport(UIKit)
import UIKit
#endif

/// Login + Register form. Styling matches the web `auth.css` one-to-one:
/// radial-purple background, 420-pt card with gradient logo tile, pill
/// tab bar, uppercase 11-pt labels, 6-pt rounded inputs with monospace
/// body text, phone input with attached country button, emoji-grid
/// avatar picker, solid accent submit, flanking "or" divider, and a
/// QR/Passkey/Seed/Link quick-login row.
@MainActor
public final class AuthViewModel: ObservableObject {
    public enum Mode { case login, register }
    public enum UiEvent: Equatable {
        case idle, submitting, error(String), loggedIn
    }

    @Published public private(set) var event: UiEvent = .idle

    private let repo: AuthRepository

    public init(repo: AuthRepository) { self.repo = repo }

    public func login(username: String, password: String) async {
        event = .submitting
        let r = await repo.login(
            username: username.trimmingCharacters(in: .whitespaces),
            password: Data(password.utf8),
        )
        event = toEvent(r)
    }

    public func register(profile: RegisterProfile) async {
        event = .submitting
        let r = await repo.registerFull(profile: profile)
        event = toEvent(r)
    }

    private func toEvent(_ r: AuthResult) -> UiEvent {
        switch r {
        case .ok: return .loggedIn
        case .error(_, let m): return .error(m)
        }
    }
}

// MARK: - Country codes ---------------------------------------------

public struct CountryDialCode: Hashable, Sendable {
    public let iso: String
    public let dialCode: String
    public let flag: String
    /// `X`-placeholder mask — same grammar as
    /// `static/js/phone_password.js::_formatPhone`: every `X` consumes
    /// one digit, everything else is literal. Extra digits past the
    /// mask end are appended as-is so country numbering exceptions
    /// don't cause truncation.
    public let format: String
    public let name: String

    public var placeholder: String {
        PhoneFormatter.apply(String(repeating: "9", count: format.filter { $0 == "X" }.count),
                             format: format)
    }
}

public enum PhoneFormatter {
    public static func apply(_ raw: String, format fmt: String) -> String {
        let digits = Array(raw.filter(\.isNumber))
        var out = ""
        var di = 0
        for ch in fmt {
            guard di < digits.count else { break }
            if ch == "X" {
                out.append(digits[di]); di += 1
            } else {
                out.append(ch)
            }
        }
        if di < digits.count { out.append(contentsOf: digits[di...]) }
        return out
    }
}

public enum PhoneDialCodes {
    public static let all: [CountryDialCode] = [
        .init(iso: "RU",  dialCode: "+7",   flag: "🇷🇺", format: "XXX XXX XX XX",  name: "Russia"),
        .init(iso: "US",  dialCode: "+1",   flag: "🇺🇸", format: "XXX XXX XXXX",   name: "United States"),
        .init(iso: "GB",  dialCode: "+44",  flag: "🇬🇧", format: "XXXX XXXXXX",    name: "United Kingdom"),
        .init(iso: "DE",  dialCode: "+49",  flag: "🇩🇪", format: "XXX XXXXXXXX",   name: "Germany"),
        .init(iso: "FR",  dialCode: "+33",  flag: "🇫🇷", format: "X XX XX XX XX",  name: "France"),
        .init(iso: "ES",  dialCode: "+34",  flag: "🇪🇸", format: "XXX XX XX XX",   name: "Spain"),
        .init(iso: "IT",  dialCode: "+39",  flag: "🇮🇹", format: "XXX XXX XXXX",   name: "Italy"),
        .init(iso: "UA",  dialCode: "+380", flag: "🇺🇦", format: "XX XXX XX XX",   name: "Ukraine"),
        .init(iso: "CN",  dialCode: "+86",  flag: "🇨🇳", format: "XXX XXXX XXXX",  name: "China"),
        .init(iso: "JP",  dialCode: "+81",  flag: "🇯🇵", format: "XX XXXX XXXX",   name: "Japan"),
        .init(iso: "KR",  dialCode: "+82",  flag: "🇰🇷", format: "XX XXXX XXXX",   name: "South Korea"),
        .init(iso: "IN",  dialCode: "+91",  flag: "🇮🇳", format: "XXXXX XXXXX",    name: "India"),
        .init(iso: "BR",  dialCode: "+55",  flag: "🇧🇷", format: "XX XXXXX XXXX",  name: "Brazil"),
        .init(iso: "MX",  dialCode: "+52",  flag: "🇲🇽", format: "XX XXXX XXXX",   name: "Mexico"),
        .init(iso: "TR",  dialCode: "+90",  flag: "🇹🇷", format: "XXX XXX XX XX",  name: "Türkiye"),
        .init(iso: "PL",  dialCode: "+48",  flag: "🇵🇱", format: "XXX XXX XXX",    name: "Poland"),
        .init(iso: "NL",  dialCode: "+31",  flag: "🇳🇱", format: "X XXXXXXXX",     name: "Netherlands"),
        .init(iso: "AU",  dialCode: "+61",  flag: "🇦🇺", format: "XXX XXX XXX",    name: "Australia"),
        .init(iso: "CA",  dialCode: "+1",   flag: "🇨🇦", format: "XXX XXX XXXX",   name: "Canada"),
        .init(iso: "AE",  dialCode: "+971", flag: "🇦🇪", format: "XX XXX XXXX",    name: "UAE"),
        .init(iso: "SA",  dialCode: "+966", flag: "🇸🇦", format: "XX XXX XXXX",    name: "Saudi Arabia"),
        .init(iso: "IL",  dialCode: "+972", flag: "🇮🇱", format: "XX XXX XXXX",    name: "Israel"),
        .init(iso: "KZ",  dialCode: "+7",   flag: "🇰🇿", format: "XXX XXX XX XX",  name: "Kazakhstan"),
    ]
}

public enum AvatarEmojis {
    public static let all: [String] = [
        "👤","🦊","🐺","🦁","🐉","🦅","🌙","⚡","🔮","🛸","💀","🌊","🔥","❄️",
        "🎭","🚀","🐱","🐶","🐼","🦄","🐙","🦋","🌺","🍄","🎮","💎","🗡️","🛡️",
        "🌈","⭐","🧠","🤖","👾","🥷","🧊",
    ]
}

// MARK: - Screen ----------------------------------------------------

public struct AuthScreen: View {
    @StateObject private var vm: AuthViewModel
    @EnvironmentObject private var loc: Localizer
    @State private var mode: AuthViewModel.Mode = .login
    private let onLoggedIn: () -> Void

    @State private var loginId = ""
    @State private var loginPw = ""

    @State private var regUsername = ""
    @State private var regCountryISO = "RU"
    @State private var regPhone = ""
    @State private var regDisplayName = ""
    @State private var regEmail = ""
    @State private var regPassword = ""
    @State private var regPasswordConfirm = ""
    @State private var regAvatarEmoji = "👤"
    @State private var regAvatarPhoto: Data?
    @State private var avatarTab = AvatarTab.emoji

    @State private var showingCountryPicker = false
    @State private var showLoginPw = false
    @State private var showRegPw = false
    @State private var showRegPw2 = false

    public init(repo: AuthRepository, onLoggedIn: @escaping () -> Void) {
        _vm = StateObject(wrappedValue: AuthViewModel(repo: repo))
        self.onLoggedIn = onLoggedIn
    }

    public var body: some View {
        ZStack {
            VortexPalette.bg.ignoresSafeArea()
            AuthBackgroundHighlights()
            ScrollView {
                // Card fills phone width with a small safe-area inset;
                // on iPad it clamps at 520pt so it doesn't stretch
                // across a 1024pt canvas.
                card
                    .frame(maxWidth: 520)
                    .padding(.horizontal, 14)
                    .padding(.top, 28)
                    .padding(.bottom, 24)
                    .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .onChange(of: vm.event) { _, new in
            if new == .loggedIn { onLoggedIn() }
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $showingCountryPicker) {
            CountryPickerSheet(selected: $regCountryISO)
        }
    }

    // MARK: Card

    private var card: some View {
        VStack(spacing: 0) {
            header
            tabs
            if mode == .login { loginForm }
            else              { registerForm }
            if case .error(let msg) = vm.event {
                Text(msg)
                    .font(.system(size: 12))
                    .foregroundStyle(VortexPalette.red)
                    .multilineTextAlignment(.center)
                    .padding(.top, 10)
            }
        }
        .padding(EdgeInsets(top: 32, leading: 22, bottom: 26, trailing: 22))
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(VortexPalette.bg2)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(VortexPalette.border, lineWidth: 1),
                ),
        )
    }

    // MARK: Header

    private var header: some View {
        VStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 16)
                .fill(LinearGradient(
                    colors: [VortexPalette.accent, VortexPalette.accent2],
                    startPoint: .topLeading, endPoint: .bottomTrailing,
                ))
                .frame(width: 56, height: 56)
                .overlay(
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 26, weight: .black))
                        .foregroundStyle(.white),
                )
                .shadow(color: VortexPalette.accent.opacity(0.25),
                        radius: 24, x: 0, y: 4)
                .padding(.bottom, 12)
            Text("VORTEX")
                .font(.system(size: 26, weight: .heavy))
                .tracking(-0.5)
                .foregroundStyle(VortexPalette.text)
            Text("Decentralized P2P messenger")
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(VortexPalette.text2)
        }
        .frame(maxWidth: .infinity)
        .padding(.bottom, 28)
    }

    // MARK: Tabs

    private var tabs: some View {
        HStack(spacing: 4) {
            tab(loc["auth.login"], .login)
            tab(loc["auth.register"], .register)
        }
        .padding(4)
        .background(VortexPalette.bg3, in: RoundedRectangle(cornerRadius: 10))
        .padding(.bottom, 20)
    }

    @ViewBuilder
    private func tab(_ title: String, _ value: AuthViewModel.Mode) -> some View {
        Button { mode = value } label: {
            Text(title)
                .font(.system(size: 13, weight: .heavy))
                .foregroundStyle(mode == value ? VortexPalette.text : VortexPalette.text2)
                .frame(maxWidth: .infinity, minHeight: 32)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(mode == value ? VortexPalette.bg2 : .clear)
                        .shadow(
                            color: mode == value ? .black.opacity(0.15) : .clear,
                            radius: 4, x: 0, y: 1,
                        ),
                )
        }
        .buttonStyle(.plain)
    }

    // MARK: Login

    private var loginForm: some View {
        VStack(spacing: 14) {
            FormField(label: loc["auth.phoneOrName"]) {
                WebInput(text: $loginId,
                         placeholder: loc.t("auth.phoneOrNamePlaceholder",
                                            default: "+15551234567 or alice"),
                         systemIcon: "person")
            }
            FormField(label: loc["auth.password"]) {
                WebPasswordInput(text: $loginPw,
                                 placeholder: "••••••••",
                                 revealed: $showLoginPw)
            }
            PrimaryButton(
                title: loc["auth.login"],
                enabled: !loginId.isEmpty && !loginPw.isEmpty && vm.event != .submitting,
            ) {
                Task { await vm.login(username: loginId, password: loginPw) }
            }
            .padding(.top, 6)
            Button(loc["auth.forgotPassword"]) {}
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(VortexPalette.accent)
                .padding(.top, 4)

            AuthDivider(text: loc.t("common.or", default: "or"))
            HStack(spacing: 10) {
                AltMethodButton(icon: "qrcode",          label: "QR")
                AltMethodButton(icon: "key.horizontal",  label: loc.t("auth.passkey", default: "Passkey"))
                AltMethodButton(icon: "leaf",            label: loc.t("auth.seed", default: "Seed"))
                AltMethodButton(icon: "link",            label: loc.t("auth.link", default: "Link"))
            }
        }
    }

    // MARK: Register

    private var registerForm: some View {
        VStack(spacing: 14) {
            FormField(label: loc["auth.username"]) {
                WebInput(text: $regUsername,
                         placeholder: loc.t("auth.usernamePlaceholder", default: "username"),
                         systemIcon: "at")
            }
            FormField(label: loc["auth.phone"]) {
                phoneField
            }
            FormField(label: loc["auth.displayName"]) {
                WebInput(text: $regDisplayName,
                         placeholder: loc.t("auth.displayNamePlaceholder", default: "Display name"),
                         systemIcon: nil)
            }
            FormField(label: loc["auth.email"], optional: true) {
                WebInput(text: $regEmail,
                         placeholder: "email@example.com",
                         systemIcon: "envelope")
            }
            FormField(label: loc["auth.passwordHint"]) {
                WebPasswordInput(text: $regPassword,
                                 placeholder: "••••••••",
                                 revealed: $showRegPw)
                PasswordStrength(password: regPassword)
                    .padding(.top, 6)
            }
            FormField(label: loc.t("auth.confirmPassword", default: "Confirm password")) {
                WebPasswordInput(text: $regPasswordConfirm,
                                 placeholder: "••••••••",
                                 revealed: $showRegPw2)
                if !regPasswordConfirm.isEmpty {
                    let match = regPasswordConfirm == regPassword
                    Text(match ? "✓ " + loc["auth.passwordsMatch"]
                               : "✗ " + loc["auth.passwordsMismatch"])
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(match ? VortexPalette.green : VortexPalette.red)
                        .padding(.top, 4)
                }
            }
            FormField(label: loc["auth.avatar"]) {
                AvatarPicker(
                    tab: $avatarTab,
                    selectedEmoji: $regAvatarEmoji,
                    selectedPhoto: $regAvatarPhoto,
                )
            }
            PrimaryButton(
                title: loc["auth.register"],
                enabled: registerValid && vm.event != .submitting,
            ) {
                Task { await submitRegister() }
            }
            .padding(.top, 6)
            Text(loc.t("auth.e2eHint",
                       default: "E2E encryption. Keys are generated on your device."))
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(VortexPalette.text3)
                .multilineTextAlignment(.center)
                .padding(.top, 8)
        }
    }

    private var phoneField: some View {
        HStack(spacing: 0) {
            Button {
                showingCountryPicker = true
            } label: {
                let c = PhoneDialCodes.all.first { $0.iso == regCountryISO }
                    ?? PhoneDialCodes.all[0]
                HStack(spacing: 4) {
                    Text(c.flag).font(.system(size: 16))
                    Text(c.dialCode).font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .foregroundStyle(VortexPalette.text)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 10))
                        .foregroundStyle(VortexPalette.text3)
                }
                .padding(.horizontal, 10).frame(height: 40)
                .background(
                    UnevenRoundedRectangle(cornerRadii: .init(
                        topLeading: 6, bottomLeading: 6,
                        bottomTrailing: 0, topTrailing: 0,
                    ))
                    .fill(VortexPalette.bg),
                )
                .overlay(
                    UnevenRoundedRectangle(cornerRadii: .init(
                        topLeading: 6, bottomLeading: 6,
                        bottomTrailing: 0, topTrailing: 0,
                    ))
                    .stroke(VortexPalette.border, lineWidth: 1),
                )
            }
            .buttonStyle(.plain)

            let country = PhoneDialCodes.all.first { $0.iso == regCountryISO }
                ?? PhoneDialCodes.all[0]
            TextField("", text: $regPhone,
                      prompt: Text(country.placeholder).foregroundColor(VortexPalette.text3))
                .textFieldStyle(.plain)
                .foregroundStyle(VortexPalette.text)
                .font(.system(size: 13, design: .monospaced))
                #if canImport(UIKit)
                .keyboardType(.phonePad)
                #endif
                // Live mask: reformat on every keystroke so the user
                // sees "900 123 45 67" instead of raw "9001234567".
                // Also re-apply when the user switches country.
                .onChange(of: regPhone) { _, new in
                    let fmt = PhoneDialCodes.all.first { $0.iso == regCountryISO }?.format
                        ?? "XXX XXX XX XX"
                    let formatted = PhoneFormatter.apply(new, format: fmt)
                    if formatted != new { regPhone = formatted }
                }
                .onChange(of: regCountryISO) { _, newISO in
                    let fmt = PhoneDialCodes.all.first { $0.iso == newISO }?.format
                        ?? "XXX XXX XX XX"
                    regPhone = PhoneFormatter.apply(regPhone, format: fmt)
                }
                .padding(.horizontal, 12).frame(height: 40)
                .background(
                    UnevenRoundedRectangle(cornerRadii: .init(
                        topLeading: 0, bottomLeading: 0,
                        bottomTrailing: 6, topTrailing: 6,
                    ))
                    .fill(VortexPalette.bg),
                )
                .overlay(
                    UnevenRoundedRectangle(cornerRadii: .init(
                        topLeading: 0, bottomLeading: 0,
                        bottomTrailing: 6, topTrailing: 6,
                    ))
                    .stroke(VortexPalette.border, lineWidth: 1),
                )
        }
    }

    private var registerValid: Bool {
        regUsername.count >= 3
            && regPassword.count >= 8
            && regPassword == regPasswordConfirm
    }

    private func submitRegister() async {
        let dial = PhoneDialCodes.all.first { $0.iso == regCountryISO }?.dialCode ?? ""
        let fullPhone = regPhone.isEmpty ? nil
            : (dial + regPhone.filter { !$0.isWhitespace })
        let profile = RegisterProfile(
            username: regUsername.trimmingCharacters(in: .whitespaces),
            password: Data(regPassword.utf8),
            phone: fullPhone,
            displayName: regDisplayName.isEmpty ? nil : regDisplayName,
            email: regEmail.isEmpty ? nil : regEmail,
            avatarEmoji: regAvatarEmoji,
            avatarPhoto: regAvatarPhoto,
        )
        await vm.register(profile: profile)
    }
}

// MARK: - Reusable atoms --------------------------------------------

private struct FormField<Content: View>: View {
    let label: String
    let optional: Bool
    @ViewBuilder let content: () -> Content
    init(label: String, optional: Bool = false, @ViewBuilder content: @escaping () -> Content) {
        self.label = label; self.optional = optional; self.content = content
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Text(label.uppercased())
                    .font(.system(size: 11, weight: .heavy))
                    .tracking(0.5)
                    .foregroundStyle(VortexPalette.text2)
                if optional {
                    Text("(optional)")
                        .font(.system(size: 10))
                        .foregroundStyle(VortexPalette.text3)
                }
            }
            content()
        }
    }
}

private struct WebInput: View {
    @Binding var text: String
    let placeholder: String
    let systemIcon: String?
    var body: some View {
        HStack(spacing: 10) {
            if let sys = systemIcon {
                Image(systemName: sys)
                    .font(.system(size: 14))
                    .foregroundStyle(VortexPalette.text3)
            }
            TextField("", text: $text,
                      prompt: Text(placeholder).foregroundColor(VortexPalette.text3))
                .textFieldStyle(.plain)
                .foregroundStyle(VortexPalette.text)
                .font(.system(size: 13, design: .monospaced))
                .autocorrectionDisabled()
                #if canImport(UIKit)
                .textInputAutocapitalization(.never)
                #endif
        }
        .padding(.horizontal, 12).frame(height: 40)
        .background(
            RoundedRectangle(cornerRadius: 6).fill(VortexPalette.bg),
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(
                    text.isEmpty ? VortexPalette.border : VortexPalette.accent.opacity(0.6),
                    lineWidth: 1,
                ),
        )
    }
}

private struct WebPasswordInput: View {
    @Binding var text: String
    let placeholder: String
    @Binding var revealed: Bool
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "lock")
                .font(.system(size: 14))
                .foregroundStyle(VortexPalette.text3)
            Group {
                if revealed {
                    TextField("", text: $text,
                              prompt: Text(placeholder).foregroundColor(VortexPalette.text3))
                } else {
                    SecureField("", text: $text,
                                prompt: Text(placeholder).foregroundColor(VortexPalette.text3))
                }
            }
            .textFieldStyle(.plain)
            .foregroundStyle(VortexPalette.text)
            .font(.system(size: 13, design: .monospaced))
            .autocorrectionDisabled()
            #if canImport(UIKit)
            .textInputAutocapitalization(.never)
            #endif
            Button { revealed.toggle() } label: {
                Image(systemName: revealed ? "eye.slash" : "eye")
                    .font(.system(size: 14))
                    .foregroundStyle(VortexPalette.text3)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12).frame(height: 40)
        .background(
            RoundedRectangle(cornerRadius: 6).fill(VortexPalette.bg),
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(
                    text.isEmpty ? VortexPalette.border : VortexPalette.accent.opacity(0.6),
                    lineWidth: 1,
                ),
        )
    }
}

/// 5-step strength meter identical to the web `pw-bar-fill`. Level is
/// a very cheap estimate — char class diversity + length — enough to
/// match the web visual; the node does its own server-side zxcvbn.
private struct PasswordStrength: View {
    let password: String
    private var level: Int {
        guard !password.isEmpty else { return 0 }
        var score = 0
        if password.count >= 8  { score += 1 }
        if password.count >= 12 { score += 1 }
        let classes = [
            password.contains { $0.isLowercase } as Bool,
            password.contains { $0.isUppercase } as Bool,
            password.contains { $0.isNumber }    as Bool,
            password.contains { !$0.isLetter && !$0.isNumber } as Bool,
        ]
        score += classes.filter { $0 }.count / 2
        return min(5, max(1, score))
    }
    private var color: Color {
        switch level {
        case 1: VortexPalette.red
        case 2: Color(red: 0xF9/255, green: 0x73/255, blue: 0x16/255)
        case 3: Color(red: 0xEA/255, green: 0xB3/255, blue: 0x08/255)
        case 4: Color(red: 0x84/255, green: 0xCC/255, blue: 0x16/255)
        default: VortexPalette.green
        }
    }
    private var label: String {
        switch level {
        case 1: "WEAK"; case 2: "FAIR"; case 3: "OK"
        case 4: "STRONG"; default: "EXCELLENT"
        }
    }
    var body: some View {
        if password.isEmpty { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 4) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(VortexPalette.bg3)
                            .frame(height: 4)
                        RoundedRectangle(cornerRadius: 2)
                            .fill(color)
                            .frame(width: geo.size.width * CGFloat(level) / 5.0, height: 4)
                    }
                }
                .frame(height: 4)
                HStack {
                    Text(label)
                        .font(.system(size: 11, weight: .heavy))
                        .tracking(0.3)
                        .foregroundStyle(color)
                    Spacer()
                    Text("\(password.count) chars")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(VortexPalette.text3)
                }
            }
        }
    }
}

private struct PrimaryButton: View {
    let title: String
    let enabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 14, weight: .heavy))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(enabled ? VortexPalette.accent : VortexPalette.bg3),
                )
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.5)
    }
}

private struct AuthDivider: View {
    let text: String
    var body: some View {
        HStack(spacing: 14) {
            Rectangle().fill(VortexPalette.border).frame(height: 1)
            Text(text)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(VortexPalette.text3)
            Rectangle().fill(VortexPalette.border).frame(height: 1)
        }
        .padding(.vertical, 8)
    }
}

private struct AltMethodButton: View {
    let icon: String
    let label: String
    var body: some View {
        Button {} label: {
            VStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundStyle(VortexPalette.text2)
                Text(label)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VortexPalette.text2)
            }
            .frame(maxWidth: .infinity, minHeight: 56)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(VortexPalette.bg)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(VortexPalette.border, lineWidth: 1),
                    ),
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Avatar picker ---------------------------------------------

enum AvatarTab { case emoji, photo }

private struct AvatarPicker: View {
    @EnvironmentObject private var loc: Localizer
    @Binding var tab: AvatarTab
    @Binding var selectedEmoji: String
    @Binding var selectedPhoto: Data?
    @State private var pickerItem: PhotosPickerItem?
    @State private var loading = false
    @State private var loadError: String?
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                tabButton(loc["auth.emoji"], value: .emoji)
                tabButton(loc["auth.photo"], value: .photo)
            }
            .overlay(
                Rectangle()
                    .fill(VortexPalette.border)
                    .frame(height: 1),
                alignment: .bottom,
            )

            if tab == .emoji {
                // No inner ScrollView — a nested vertical scroll would
                // hijack gestures from the outer auth-form ScrollView
                // and the page would stop scrolling past this field.
                // 35 emojis at 8 per row = 5 rows × ~38pt = 190pt, so
                // an inline LazyVGrid is small enough to show in full.
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 8),
                          spacing: 2) {
                    ForEach(AvatarEmojis.all, id: \.self) { e in
                        Button { selectedEmoji = e } label: {
                            Text(e)
                                .font(.system(size: 18))
                                .frame(width: 36, height: 36)
                                .background(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(
                                            selectedEmoji == e ? VortexPalette.accent : .clear,
                                            lineWidth: 2,
                                        )
                                        .background(
                                            RoundedRectangle(cornerRadius: 8)
                                                .fill(
                                                    selectedEmoji == e
                                                        ? VortexPalette.accent.opacity(0.1)
                                                        : .clear,
                                                ),
                                        ),
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(10)
            } else {
                VStack(spacing: 12) {
                    // PhotosPicker wraps a dashed-circle preview. Tapping
                    // the circle triggers the system picker; once the
                    // user chooses a photo we load it as Data via
                    // `loadTransferable(type: Data.self)` and keep it
                    // in `selectedPhoto` — the register form then
                    // uploads it to /api/authentication/avatar.
                    PhotosPicker(selection: $pickerItem,
                                 matching: .images,
                                 photoLibrary: .shared()) {
                        avatarCircle
                    }
                    .buttonStyle(.plain)
                    .onChange(of: pickerItem) { _, item in
                        guard let item else { return }
                        loading = true; loadError = nil
                        Task {
                            do {
                                if let data = try await item.loadTransferable(type: Data.self) {
                                    selectedPhoto = Self.downscaled(data, max: 512)
                                }
                            } catch {
                                loadError = (error as NSError).localizedDescription
                            }
                            loading = false
                        }
                    }
                    if selectedPhoto != nil {
                        Button(loc.t("auth.removePhoto", default: "Remove photo")) {
                            selectedPhoto = nil
                            pickerItem = nil
                        }
                        .font(.system(size: 11, design: .monospaced))
                        .tint(VortexPalette.text2)
                    } else {
                        Text(loc.t("auth.selectPhoto",
                                   default: "Tap to choose from gallery"))
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(VortexPalette.text3)
                    }
                    if let e = loadError {
                        Text(e)
                            .font(.system(size: 11))
                            .foregroundStyle(VortexPalette.red)
                            .multilineTextAlignment(.center)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(16)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 10).fill(VortexPalette.bg),
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10).stroke(VortexPalette.border, lineWidth: 1),
        )
    }

    @ViewBuilder
    private var avatarCircle: some View {
        ZStack {
            Circle()
                .fill(VortexPalette.bg3)
                .overlay(
                    Circle().stroke(
                        selectedPhoto == nil ? VortexPalette.border : VortexPalette.accent,
                        style: StrokeStyle(
                            lineWidth: 2,
                            dash: selectedPhoto == nil ? [4] : [],
                        ),
                    ),
                )
                .frame(width: 84, height: 84)
            #if canImport(UIKit)
            if let data = selectedPhoto, let ui = UIImage(data: data) {
                Image(uiImage: ui)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 80, height: 80)
                    .clipShape(Circle())
            } else if loading {
                ProgressView().tint(.white)
            } else {
                Image(systemName: "camera")
                    .font(.system(size: 24))
                    .foregroundStyle(VortexPalette.text3)
            }
            #else
            Image(systemName: "camera")
                .font(.system(size: 24))
                .foregroundStyle(VortexPalette.text3)
            #endif
        }
    }

    /// Re-encode the picked image at ≤maxPx on the long side as JPEG
    /// q=0.85. The backend caps uploads at 5 MB and downsizes to 256×256
    /// anyway, so there's no point sending a 12 MP HEIC through the
    /// cloudflared tunnel — this halves typical first-register traffic.
    static func downscaled(_ data: Data, max: CGFloat) -> Data {
        #if canImport(UIKit)
        guard let img = UIImage(data: data) else { return data }
        let w = img.size.width, h = img.size.height
        let scale = min(1, max / Swift.max(w, h))
        if scale >= 1 {
            return img.jpegData(compressionQuality: 0.85) ?? data
        }
        let sz = CGSize(width: w * scale, height: h * scale)
        let renderer = UIGraphicsImageRenderer(size: sz)
        let resized = renderer.image { _ in
            img.draw(in: CGRect(origin: .zero, size: sz))
        }
        return resized.jpegData(compressionQuality: 0.85) ?? data
        #else
        return data
        #endif
    }

    @ViewBuilder
    private func tabButton(_ title: String, value: AvatarTab) -> some View {
        Button { tab = value } label: {
            VStack(spacing: 4) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(tab == value ? VortexPalette.text : VortexPalette.text2)
                Rectangle()
                    .fill(tab == value ? VortexPalette.accent : .clear)
                    .frame(height: 2)
                    .padding(.horizontal, 20)
            }
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Background + country sheet --------------------------------

private struct AuthBackgroundHighlights: View {
    var body: some View {
        GeometryReader { geo in
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [VortexPalette.accent.opacity(0.08), .clear],
                            center: .center, startRadius: 0, endRadius: 500,
                        ),
                    )
                    .frame(width: 800, height: 800)
                    .position(x: geo.size.width * 0.2, y: geo.size.height * 0.5)
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [VortexPalette.accent2.opacity(0.06), .clear],
                            center: .center, startRadius: 0, endRadius: 400,
                        ),
                    )
                    .frame(width: 700, height: 700)
                    .position(x: geo.size.width * 0.8, y: geo.size.height * 0.2)
            }
        }
        .ignoresSafeArea()
    }
}

private struct CountryPickerSheet: View {
    @Binding var selected: String
    @Environment(\.dismiss) private var dismiss
    @State private var query: String = ""
    var body: some View {
        NavigationStack {
            List {
                ForEach(filtered, id: \.iso) { c in
                    Button {
                        selected = c.iso
                        dismiss()
                    } label: {
                        HStack(spacing: 10) {
                            Text(c.flag).font(.system(size: 18))
                            Text(c.name)
                                .font(.system(size: 13))
                                .foregroundStyle(VortexPalette.text)
                                .lineLimit(1)
                            Spacer()
                            Text(c.dialCode)
                                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                                .foregroundStyle(VortexPalette.text3)
                            if c.iso == selected {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 12, weight: .bold))
                                    .foregroundStyle(VortexPalette.accent)
                            }
                        }
                    }
                    .listRowBackground(VortexPalette.bg2)
                }
            }
            .scrollContentBackground(.hidden)
            .background(VortexPalette.bg)
            .searchable(text: $query)
            .navigationTitle("Country code")
        }
    }
    private var filtered: [CountryDialCode] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        guard !q.isEmpty else { return PhoneDialCodes.all }
        return PhoneDialCodes.all.filter {
            $0.iso.lowercased().contains(q)
                || $0.dialCode.contains(q)
                || $0.name.lowercased().contains(q)
        }
    }
}
