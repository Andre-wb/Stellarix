import SwiftUI

/// Compact grid-based emoji picker. Tabs at the top (🕑 😀 👋 …), a
/// search field, and a 8-column LazyVGrid underneath. Tapping an emoji
/// calls [onPick] and bumps it to the front of the "recent" ring.
public struct EmojiPickerView: View {
    @ObservedObject private var vm: EmojiPickerVM
    private let onPick: (String) -> Void

    public init(catalog: EmojiCatalog, onPick: @escaping (String) -> Void) {
        self.vm = EmojiPickerVM(catalog: catalog)
        self.onPick = onPick
    }

    public var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 6) {
                ForEach(vm.tabs, id: \.self) { cat in
                    Button {
                        vm.select(cat)
                    } label: {
                        Text(cat.tabIcon)
                            .font(.title3)
                            .padding(6)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(vm.current == cat ? Color.white.opacity(0.12) : .clear)
                            )
                    }
                    .accessibilityLabel("emoji.category.\(cat.rawValue)")
                }
            }
            .padding(.horizontal, 8)

            TextField("search", text: $vm.query)
                .textFieldStyle(.roundedBorder)
                .padding(.horizontal, 8)
                .accessibilityLabel("emoji.search")

            ScrollView {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 8),
                          spacing: 8) {
                    ForEach(vm.visible, id: \.self) { e in
                        Button {
                            vm.catalog.bumpRecent(e)
                            onPick(e)
                        } label: {
                            Text(e).font(.title2)
                        }
                        .accessibilityLabel(e)
                    }
                }
                .padding(8)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 260, maxHeight: 360)
        .background(Color(red: 0x0F/255, green: 0x0F/255, blue: 0x17/255))
    }
}

@MainActor
final class EmojiPickerVM: ObservableObject {
    @Published var current: EmojiCategory = .recent
    @Published var query: String = "" {
        didSet { recompute() }
    }
    @Published private(set) var visible: [String] = []
    let catalog: EmojiCatalog
    let tabs: [EmojiCategory]

    init(catalog: EmojiCatalog) {
        self.catalog = catalog
        self.tabs = catalog.categories()
        let recent = catalog.recent()
        self.current = recent.isEmpty ? .smileys : .recent
        recompute()
    }

    func select(_ cat: EmojiCategory) {
        current = cat
        recompute()
    }

    private func recompute() {
        if !query.trimmingCharacters(in: .whitespaces).isEmpty {
            visible = catalog.search(query)
        } else {
            visible = catalog.emojis(in: current)
        }
    }
}
