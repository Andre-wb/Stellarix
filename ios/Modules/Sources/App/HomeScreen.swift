import SwiftUI
import VortexCrypto

/// Wave 2 landing screen — now shows a freshly-generated Ed25519 + X25519
/// pubkey, proving the crypto stack is wired end-to-end. Wave 3 replaces
/// this with the real bootstrap flow.
public struct HomeScreen: View {
    private let baseUrl: String
    private let env: AppEnvironment

    public init(baseUrl: String = "", env: AppEnvironment = .shared) {
        self.baseUrl = baseUrl
        self.env = env
    }

    public var body: some View {
        ZStack {
            VortexPalette.background.ignoresSafeArea()
            VStack(spacing: 14) {
                Circle()
                    .fill(VortexPalette.purple)
                    .frame(width: 12, height: 12)
                Text("VORTEX")
                    .font(.system(size: 32, weight: .bold))
                    .foregroundStyle(VortexPalette.text)
                Text("v\(env.version)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(VortexPalette.text2)
                Text("Wave 2 — crypto wired")
                    .font(.footnote)
                    .foregroundStyle(VortexPalette.text2)
                    .padding(.top, 18)
                Text("X25519 \(env.cryptoPreview.x25519Short)…")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(VortexPalette.text2)
                    .padding(.top, 6)
                Text("Ed25519 \(env.cryptoPreview.ed25519Short)…")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(VortexPalette.text2)
            }
        }
        .preferredColorScheme(.dark)
    }
}

enum VortexPalette {
    static let background = Color(red: 0x07 / 255, green: 0x07 / 255, blue: 0x0E / 255)
    static let surface    = Color(red: 0x0D / 255, green: 0x0D / 255, blue: 0x1A / 255)
    static let text       = Color(red: 0xF2 / 255, green: 0xF2 / 255, blue: 0xF8 / 255)
    static let text2      = Color(red: 0x88 / 255, green: 0x88 / 255, blue: 0xAA / 255)
    static let purple     = Color(red: 0x7C / 255, green: 0x3A / 255, blue: 0xED / 255)
    static let cyan       = Color(red: 0x06 / 255, green: 0xD6 / 255, blue: 0xF0 / 255)
}

#Preview {
    HomeScreen()
}
