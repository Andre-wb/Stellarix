import SwiftUI

@MainActor
public final class PremiumViewModel: ObservableObject {
    @Published public private(set) var status: PremiumStatus?
    @Published public private(set) var busy = false
    @Published public var checkoutURL: URL?
    private let repo: Premium

    public init(repo: Premium) { self.repo = repo }

    public func refresh() async { status = await repo.status() }

    public func upgrade(_ tier: String) async {
        busy = true
        if let s = await repo.startCheckout(tier: tier), let u = URL(string: s.url) {
            checkoutURL = u
        }
        busy = false
    }

    public func cancel() async {
        busy = true
        _ = await repo.cancel()
        status = await repo.status()
        busy = false
    }
}

public struct PremiumScreen: View {
    @StateObject private var vm: PremiumViewModel
    @Environment(\.openURL) private var openURL

    public init(repo: Premium) {
        _vm = StateObject(wrappedValue: PremiumViewModel(repo: repo))
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your plan").font(.headline).foregroundStyle(.secondary)
            let tier = vm.status?.tier ?? "free"
            VStack(alignment: .leading, spacing: 6) {
                Text(tier.capitalized).font(.largeTitle.bold())
                if let f = vm.status?.features, !f.isEmpty {
                    Text("Features: \(f.joinToString())")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))

            if tier == "free" {
                Button("Upgrade to Plus") { Task { await vm.upgrade("plus") } }
                    .buttonStyle(.borderedProminent)
                    .disabled(vm.busy)
                Button("Upgrade to Pro") { Task { await vm.upgrade("pro") } }
                    .buttonStyle(.bordered)
                    .disabled(vm.busy)
            } else {
                Button("Cancel subscription", role: .destructive) { Task { await vm.cancel() } }
                    .disabled(vm.busy)
            }
            Spacer()
        }
        .padding()
        .navigationTitle("Premium")
        .task { await vm.refresh() }
        .onChange(of: vm.checkoutURL) { _, url in
            if let u = url { openURL(u); vm.checkoutURL = nil }
        }
    }
}

private extension Array where Element == String {
    func joinToString() -> String { self.joined(separator: ", ") }
}
