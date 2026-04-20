import SwiftUI

/// Wave 3 bootstrap flow.
///
/// 1. On first appearance the view model probes the primary controller
///    URL (vortexx.sol). While the probe is in flight we show a spinner.
/// 2. Success ⇒ persist the base URL in [NodePreferences] and emit
///    `onConnected` — the parent navigator moves to Auth.
/// 3. Failure ⇒ render the manual-entry form, `Connect` triggers probe.
@MainActor
public final class BootstrapViewModel: ObservableObject {

    public enum State: Equatable {
        case probing
        case needsUrl(lastError: String?)
        case ready(String)
    }

    @Published public private(set) var state: State = .probing

    private let directory: NodeDirectory
    private let prefs: NodePreferences

    public init(directory: NodeDirectory, prefs: NodePreferences) {
        self.directory = directory
        self.prefs = prefs
    }

    public func start() {
        if let saved = prefs.currentBaseUrl(), !saved.isEmpty {
            state = .ready(saved)
            return
        }
        Task { await probePrimary() }
    }

    public func probePrimary() async {
        state = .probing
        switch await directory.probePrimary() {
        case .ok(let baseUrl, _): commit(baseUrl)
        case .unreachable(_, let reason): state = .needsUrl(lastError: reason)
        }
    }

    public func probe(_ url: String) async {
        state = .probing
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
            Color(red: 0x07/255, green: 0x07/255, blue: 0x0E/255).ignoresSafeArea()
            VStack(spacing: 14) {
                Circle()
                    .fill(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255))
                    .frame(width: 10, height: 10)
                Text("VORTEX").font(.title3.bold()).foregroundStyle(.white)
                switch vm.state {
                case .probing:
                    ProgressView().tint(.white).padding(.top, 16)
                    Text("connecting to vortexx.sol…")
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.55))
                case .needsUrl(let last):
                    ManualUrlForm(lastError: last,
                                  onProbe: { url in Task { await vm.probe(url) } },
                                  onRetry: { Task { await vm.probePrimary() } })
                case .ready(let url):
                    Color.clear.onAppear { onConnected(url) }
                }
            }
            .padding(24)
        }
        .onAppear { vm.start() }
        .preferredColorScheme(.dark)
    }
}

private struct ManualUrlForm: View {
    let lastError: String?
    let onProbe: (String) -> Void
    let onRetry: () -> Void
    @State private var input = ""

    var body: some View {
        VStack(spacing: 12) {
            Text("Can't reach vortexx.sol.\(lastError.map { "\n(\($0))" } ?? "")")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)
            TextField("Mirror or node URL",
                      text: $input,
                      prompt: Text("https://mirror.example.com").foregroundColor(.gray))
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
            Button("Connect") { onProbe(input) }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255))
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
            Button("Retry vortexx.sol", action: onRetry)
                .font(.footnote)
                .tint(.white.opacity(0.6))
        }
        .padding(.top, 24)
    }
}
