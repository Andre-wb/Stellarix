import SwiftUI

/// Bootstrap flow:
///   0. `chooseMode` — three-way picker: official, mirror, LAN discovery.
///   1. `probing` — hitting /v1/integrity, spinner on screen.
///   2. `needsUrl` — probe failed, user types a URL manually.
///   3. `discovering` — Bonjour browser looking for `_vortex._tcp`
///      instances on the local network, then offers a list.
///   4. `ready` — success, parent navigator moves to Auth.
@MainActor
public final class BootstrapViewModel: ObservableObject {

    public enum State: Equatable {
        case chooseMode
        case probing(label: String)
        case needsUrl(lastError: String?)
        case discovering
        case discovered([DiscoveredNode])
        case ready(String)
    }

    public struct DiscoveredNode: Equatable, Hashable, Identifiable {
        public let name: String
        public let url: String
        public var id: String { url }
    }

    @Published public private(set) var state: State = .chooseMode

    private let directory: NodeDirectory
    private let prefs: NodePreferences
    private var browser: LANBrowser?

    public init(directory: NodeDirectory, prefs: NodePreferences) {
        self.directory = directory
        self.prefs = prefs
    }

    /// Called on first appearance. If we already have a saved base
    /// URL, short-circuit to `ready` — no need to re-ask the user.
    public func start() {
        if let saved = prefs.currentBaseUrl(), !saved.isEmpty {
            state = .ready(saved)
        }
    }

    public func chooseOfficial() {
        Task { await probePrimary() }
    }

    public func chooseMirror() {
        state = .needsUrl(lastError: nil)
    }

    public func chooseDiscover() {
        state = .discovering
        Task {
            let b = LANBrowser()
            browser = b
            let found = await b.browse(timeout: 5)
            state = .discovered(found)
        }
    }

    public func backToModes() {
        browser?.stop(); browser = nil
        state = .chooseMode
    }

    public func probePrimary() async {
        state = .probing(label: "connecting to vortexx.sol…")
        switch await directory.probePrimary() {
        case .ok(let baseUrl, _): commit(baseUrl)
        case .unreachable(_, let reason): state = .needsUrl(lastError: reason)
        }
    }

    public func probe(_ url: String) async {
        state = .probing(label: "probing \(url)…")
        switch await directory.probe(url: url) {
        case .ok(let baseUrl, _): commit(baseUrl)
        case .unreachable(_, let reason): state = .needsUrl(lastError: reason)
        }
    }

    private func commit(_ url: String) {
        prefs.setBaseUrl(url)
        state = .ready(url)
    }
}

public struct BootstrapScreen: View {
    @StateObject private var vm: BootstrapViewModel
    private let onConnected: (String) -> Void

    public init(
        directory: NodeDirectory,
        prefs: NodePreferences,
        onConnected: @escaping (String) -> Void,
    ) {
        _vm = StateObject(wrappedValue: BootstrapViewModel(directory: directory, prefs: prefs))
        self.onConnected = onConnected
    }

    public var body: some View {
        ZStack {
            Color(red: 0x07/255, green: 0x06/255, blue: 0x0E/255).ignoresSafeArea()
            BootstrapOrbs()
            VStack(spacing: 20) {
                header
                switch vm.state {
                case .chooseMode:
                    modePicker
                case .probing(let label):
                    ProgressView().tint(.white).padding(.top, 16)
                    Text(label)
                        .font(.footnote).foregroundStyle(.white.opacity(0.55))
                    Button("Cancel") { vm.backToModes() }
                        .font(.footnote).tint(.white.opacity(0.5))
                case .needsUrl(let last):
                    ManualUrlForm(
                        lastError: last,
                        onProbe: { url in Task { await vm.probe(url) } },
                        onRetry: { Task { await vm.probePrimary() } },
                        onBack: { vm.backToModes() },
                    )
                case .discovering:
                    ProgressView().tint(.white).padding(.top, 16)
                    Text("scanning local network…")
                        .font(.footnote).foregroundStyle(.white.opacity(0.55))
                    Button("Cancel") { vm.backToModes() }
                        .font(.footnote).tint(.white.opacity(0.5))
                case .discovered(let list):
                    DiscoveredList(
                        nodes: list,
                        onPick: { url in Task { await vm.probe(url) } },
                        onBack: { vm.backToModes() },
                    )
                case .ready(let url):
                    Color.clear.onAppear { onConnected(url) }
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 20).padding(.vertical, 32)
        }
        .onAppear { vm.start() }
        .preferredColorScheme(.dark)
    }

    // MARK: Header wordmark

    private var header: some View {
        VStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 14)
                .fill(LinearGradient(
                    colors: [
                        Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255),
                        Color(red: 0x4E/255, green: 0xCD/255, blue: 0xC4/255),
                    ],
                    startPoint: .topLeading, endPoint: .bottomTrailing,
                ))
                .frame(width: 56, height: 56)
                .overlay(
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 26, weight: .black))
                        .foregroundStyle(.white),
                )
                .shadow(color: Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255).opacity(0.4),
                        radius: 24, x: 0, y: 4)
            Text("VORTEX")
                .font(.system(size: 28, weight: .black))
                .tracking(6)
                .foregroundStyle(.white)
            Text("Decentralized P2P messenger")
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(.white.opacity(0.45))
        }
    }

    // MARK: Mode picker

    private var modePicker: some View {
        VStack(spacing: 12) {
            Text("How do you want to connect?")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white.opacity(0.75))
                .padding(.bottom, 4)

            ModeButton(
                icon: "globe",
                title: "vortexx.sol",
                subtitle: "Official public entry",
                primary: true,
                action: { vm.chooseOfficial() },
            )

            ModeButton(
                icon: "link",
                title: "Mirror / custom URL",
                subtitle: "Paste a node or mirror address",
                action: { vm.chooseMirror() },
            )

            ModeButton(
                icon: "wifi",
                title: "Find nodes on this network",
                subtitle: "Bonjour discovery on your LAN",
                action: { vm.chooseDiscover() },
            )
        }
    }
}

// MARK: - Mode button ------------------------------------------------

private struct ModeButton: View {
    let icon: String
    let title: String
    let subtitle: String
    var primary: Bool = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(primary
                              ? Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255)
                              : Color.white.opacity(0.06))
                        .frame(width: 44, height: 44)
                    Image(systemName: icon)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundStyle(.white)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 15, weight: .heavy))
                        .foregroundStyle(.white)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(.white.opacity(0.55))
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.35))
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.white.opacity(primary ? 0.03 : 0.02))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(
                                primary
                                    ? Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255).opacity(0.5)
                                    : Color.white.opacity(0.08),
                                lineWidth: 1,
                            ),
                    ),
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Manual URL form -------------------------------------------

private struct ManualUrlForm: View {
    let lastError: String?
    let onProbe: (String) -> Void
    let onRetry: () -> Void
    let onBack: () -> Void
    @State private var input = ""

    var body: some View {
        VStack(spacing: 14) {
            if let last = lastError {
                Text("Couldn't reach that address.\n(\(last))")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.6))
                    .multilineTextAlignment(.center)
            } else {
                Text("Paste a mirror or node URL")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.6))
            }
            TextField("Mirror or node URL",
                      text: $input,
                      prompt: Text("https://…trycloudflare.com").foregroundColor(.gray))
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                #if canImport(UIKit)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                #endif
            Button("Connect") { onProbe(input) }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255))
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
            HStack {
                Button("Retry vortexx.sol", action: onRetry)
                    .font(.footnote).tint(.white.opacity(0.6))
                Spacer()
                Button("Back", action: onBack)
                    .font(.footnote).tint(.white.opacity(0.6))
            }
        }
    }
}

// MARK: - Discovered list -------------------------------------------

private struct DiscoveredList: View {
    let nodes: [BootstrapViewModel.DiscoveredNode]
    let onPick: (String) -> Void
    let onBack: () -> Void
    var body: some View {
        VStack(spacing: 12) {
            if nodes.isEmpty {
                Text("No nodes found on this network.")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.6))
                Text("Ask the operator to start a node on your Wi-Fi, or paste a mirror URL.")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.4))
                    .multilineTextAlignment(.center)
            } else {
                Text("Found \(nodes.count) node\(nodes.count == 1 ? "" : "s")")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.6))
                ScrollView {
                    VStack(spacing: 8) {
                        ForEach(nodes) { n in
                            Button {
                                onPick(n.url)
                            } label: {
                                HStack {
                                    Image(systemName: "network")
                                        .foregroundStyle(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255))
                                    VStack(alignment: .leading) {
                                        Text(n.name)
                                            .font(.system(size: 14, weight: .bold))
                                            .foregroundStyle(.white)
                                        Text(n.url)
                                            .font(.system(size: 11, design: .monospaced))
                                            .foregroundStyle(.white.opacity(0.5))
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .foregroundStyle(.white.opacity(0.35))
                                }
                                .padding(12)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Color.white.opacity(0.04))
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 10)
                                                .stroke(Color.white.opacity(0.08), lineWidth: 1),
                                        ),
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .frame(maxHeight: 280)
            }
            Button("Back", action: onBack)
                .font(.footnote).tint(.white.opacity(0.6))
                .padding(.top, 6)
        }
    }
}

// MARK: - Orb background --------------------------------------------

private struct BootstrapOrbs: View {
    var body: some View {
        GeometryReader { geo in
            ZStack {
                blob(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255),
                     at: CGPoint(x: geo.size.width * 0.1, y: geo.size.height * 0.15), size: 420)
                blob(Color(red: 0x06/255, green: 0xB6/255, blue: 0xD4/255),
                     at: CGPoint(x: geo.size.width * 0.95, y: geo.size.height * 0.9), size: 380)
            }
        }
        .ignoresSafeArea()
        .opacity(0.3)
    }
    private func blob(_ color: Color, at p: CGPoint, size: CGFloat) -> some View {
        Circle()
            .fill(
                RadialGradient(colors: [color, .clear],
                               center: .center, startRadius: 0, endRadius: size / 2),
            )
            .frame(width: size, height: size)
            .blur(radius: 70)
            .position(p)
    }
}

// MARK: - Bonjour browser -------------------------------------------

/// Minimal Bonjour scanner. Looks for `_vortex._tcp` service type — a
/// node advertises itself as `_vortex._tcp.local.` on startup (Android
/// uses the same spec via NSD). For each resolved instance we build
/// `http(s)://host:port` from the TXT record (or fall back to the
/// plain socket address) so the user never has to know the IP.
final class LANBrowser: NSObject, NetServiceBrowserDelegate, NetServiceDelegate, @unchecked Sendable {
    private let browser = NetServiceBrowser()
    private var pending: [NetService] = []
    private var found: [BootstrapViewModel.DiscoveredNode] = []
    private var continuation: CheckedContinuation<[BootstrapViewModel.DiscoveredNode], Never>?
    private let lock = NSLock()

    override init() {
        super.init()
        browser.delegate = self
    }

    func browse(timeout: TimeInterval) async -> [BootstrapViewModel.DiscoveredNode] {
        return await withCheckedContinuation { [weak self] cont in
            guard let self else { cont.resume(returning: []); return }
            self.continuation = cont
            DispatchQueue.main.async {
                self.browser.searchForServices(ofType: "_vortex._tcp.", inDomain: "local.")
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + timeout) { [weak self] in
                self?.finish()
            }
        }
    }

    func stop() {
        browser.stop()
        finish()
    }

    private func finish() {
        lock.lock()
        let list = found
        let c = continuation
        continuation = nil
        lock.unlock()
        c?.resume(returning: list)
    }

    // NetServiceBrowserDelegate

    func netServiceBrowser(_ browser: NetServiceBrowser,
                           didFind service: NetService,
                           moreComing: Bool) {
        service.delegate = self
        pending.append(service)
        service.resolve(withTimeout: 3)
    }

    // NetServiceDelegate

    func netServiceDidResolveAddress(_ sender: NetService) {
        let host = sender.hostName ?? ""
        let port = sender.port
        guard !host.isEmpty, port > 0 else { return }
        let trimmedHost = host.hasSuffix(".") ? String(host.dropLast()) : host
        let url = "http://\(trimmedHost):\(port)"
        lock.lock()
        found.append(.init(name: sender.name, url: url))
        lock.unlock()
    }

    func netService(_ sender: NetService, didNotResolve errorDict: [String: NSNumber]) {
        // Ignore: individual resolution failures are non-fatal.
    }
}
