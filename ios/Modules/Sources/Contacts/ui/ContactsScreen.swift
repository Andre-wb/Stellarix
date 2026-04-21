import SwiftUI

@MainActor
public final class ContactsViewModel: ObservableObject {
    @Published public private(set) var contacts: [Contact] = []
    @Published public var query: String = ""
    @Published public private(set) var results: [Contact] = []
    private let repo: Contacts

    public init(repo: Contacts) { self.repo = repo }

    public func refresh() async { contacts = await repo.list() }

    public func search() async {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { results = []; return }
        results = await repo.search(q)
    }

    public func add(username: String) async {
        if let added = await repo.add(username: username) {
            contacts.append(added)
        }
    }

    public func remove(_ id: Int64) async {
        await repo.remove(id: id)
        contacts.removeAll { $0.id == id }
    }
}

public struct ContactsScreen: View {
    @StateObject private var vm: ContactsViewModel
    @State private var showAdd = false
    @State private var newUsername = ""
    private let onOpenDm: (Int64) -> Void

    public init(repo: Contacts, onOpenDm: @escaping (Int64) -> Void = { _ in }) {
        _vm = StateObject(wrappedValue: ContactsViewModel(repo: repo))
        self.onOpenDm = onOpenDm
    }

    private var visible: [Contact] {
        vm.query.trimmingCharacters(in: .whitespaces).isEmpty ? vm.contacts : vm.results
    }

    public var body: some View {
        List(visible) { c in
            Button {
                onOpenDm(c.id)
            } label: {
                ContactRowView(contact: c)
            }
            .swipeActions(edge: .trailing) {
                Button(role: .destructive) {
                    Task { await vm.remove(c.id) }
                } label: { Label("Remove", systemImage: "trash") }
            }
        }
        .navigationTitle("Contacts")
        .searchable(text: $vm.query)
        .onChange(of: vm.query) { _, _ in Task { await vm.search() } }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button { showAdd = true } label: { Image(systemName: "person.badge.plus") }
            }
        }
        .task { await vm.refresh() }
        .alert("Add contact", isPresented: $showAdd) {
            TextField("username or +phone", text: $newUsername)
                #if canImport(UIKit)
                .textInputAutocapitalization(.never)
                #endif
                .autocorrectionDisabled()
            Button("Add") {
                let n = newUsername
                newUsername = ""
                Task { await vm.add(username: n) }
            }
            Button("Cancel", role: .cancel) { newUsername = "" }
        }
    }
}

private struct ContactRowView: View {
    let contact: Contact
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle().fill(Color.white.opacity(0.08)).frame(width: 36, height: 36)
                Text(String(contact.username.prefix(1)).uppercased())
            }
            VStack(alignment: .leading) {
                Text(contact.displayName ?? contact.username).foregroundStyle(.white)
                Text("@\(contact.username)").font(.caption2).foregroundStyle(.secondary)
            }
            Spacer()
        }
    }
}
