import SwiftUI

/// Personal saved-GIF collection (no Tenor). Tapping a tile calls
/// [onPick] with the URL; the composer pastes it into the message or
/// attaches as a file. Add by pasting any .gif URL.
@MainActor
public final class SavedGifsViewModel: ObservableObject {
    @Published public private(set) var gifs: [SavedGif] = []
    @Published public var urlInput: String = ""
    @Published public private(set) var adding = false
    private let repo: SavedGifs

    public init(repo: SavedGifs) { self.repo = repo }

    public func refresh() async {
        gifs = await repo.list()
    }

    public func addFromUrl() async {
        let u = urlInput.trimmingCharacters(in: .whitespaces)
        guard !u.isEmpty else { return }
        adding = true
        if let added = await repo.add(url: u, width: 0, height: 0) {
            gifs.append(added)
        }
        urlInput = ""
        adding = false
    }

    public func remove(_ id: Int64) async {
        await repo.remove(id: id)
        gifs.removeAll { $0.id == id }
    }
}

public struct SavedGifsSheet: View {
    @StateObject private var vm: SavedGifsViewModel
    private let onPick: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    public init(repo: SavedGifs, onPick: @escaping (String) -> Void) {
        _vm = StateObject(wrappedValue: SavedGifsViewModel(repo: repo))
        self.onPick = onPick
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 8) {
                HStack {
                    TextField("Paste a .gif URL", text: $vm.urlInput)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityLabel("gif.url")
                    Button("Add") { Task { await vm.addFromUrl() } }
                        .disabled(vm.urlInput.trimmingCharacters(in: .whitespaces).isEmpty || vm.adding)
                }
                .padding(.horizontal, 12)

                if vm.gifs.isEmpty {
                    Spacer()
                    Text("No saved GIFs yet.")
                        .foregroundStyle(.secondary)
                    Spacer()
                } else {
                    ScrollView {
                        LazyVGrid(
                            columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 3),
                            spacing: 8,
                        ) {
                            ForEach(vm.gifs) { g in
                                Button {
                                    onPick(g.url); dismiss()
                                } label: {
                                    VStack(spacing: 4) {
                                        Text("🎬").font(.title)
                                        Text((g.url as NSString).lastPathComponent)
                                            .font(.caption2).lineLimit(1)
                                            .foregroundStyle(.secondary)
                                    }
                                    .frame(minHeight: 80)
                                    .frame(maxWidth: .infinity)
                                    .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 8))
                                }
                                .contextMenu {
                                    Button(role: .destructive) {
                                        Task { await vm.remove(g.id) }
                                    } label: { Label("Remove", systemImage: "trash") }
                                }
                            }
                        }
                        .padding(12)
                    }
                }
            }
            .navigationTitle("Saved GIFs")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Button("Close") { dismiss() }
                }
            }
            .task { await vm.refresh() }
        }
    }
}
