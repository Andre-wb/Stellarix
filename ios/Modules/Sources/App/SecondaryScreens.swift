import SwiftUI
import Auth
import Identity
import Settings
import Spaces
import Bots
import Search
import Threads
import Feeds
import I18N
import DB

// MARK: Settings ------------------------------------------------------

public struct SettingsScreen: View {
    private let store: SettingsStore
    private let identity: IdentityRepository
    private let auth: AuthRepository
    @State private var showPanic = false

    public init(store: SettingsStore, identity: IdentityRepository, auth: AuthRepository) {
        self.store = store; self.identity = identity; self.auth = auth
    }

    public var body: some View {
        Form {
            Section("Notifications") {
                Toggle("Enabled", isOn: .constant(true))
            }
            Section("Session") {
                Button("Sign out") { Task { await auth.logout() } }
            }
            Section("Danger") {
                Button("Wipe all local data", role: .destructive) { showPanic = true }
            }
        }
        .navigationTitle("Settings")
        .alert("Wipe everything?", isPresented: $showPanic) {
            Button("Cancel", role: .cancel) {}
            Button("Wipe", role: .destructive) { Task { await store.wipeAll() } }
        } message: {
            Text("Destroys local keys, cached messages, and session. The server-side panic action is not triggered.")
        }
    }
}

// MARK: Spaces --------------------------------------------------------

public struct SpacesScreen: View {
    private let repo: SpacesRepository
    @State private var items: [Space] = []
    public init(repo: SpacesRepository) { self.repo = repo }

    public var body: some View {
        List(items, id: \.id) { s in
            HStack {
                Text(s.avatarEmoji)
                VStack(alignment: .leading) {
                    Text(s.name)
                    Text("\(s.memberCount) members\(s.isPublic ? " · public" : "")")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Spaces")
        .task {
            _ = await repo.refresh()
            for await rows in repo.spaces { items = rows }
        }
    }
}

// MARK: Bots ----------------------------------------------------------

public struct BotsScreen: View {
    private let repo: BotsRepository
    @State private var items: [Bot] = []
    public init(repo: BotsRepository) { self.repo = repo }

    public var body: some View {
        List(items, id: \.id) { b in
            HStack {
                VStack(alignment: .leading) {
                    Text(b.name).bold()
                    Text("by \(b.author)").font(.caption).foregroundStyle(.secondary)
                    Text(b.shortDescription).font(.caption)
                }
                Spacer()
                if b.installed {
                    Button("Remove", role: .destructive) { Task { _ = await repo.uninstall(b.id) } }
                } else {
                    Button("Install") { Task { _ = await repo.install(b.id) } }
                }
            }
        }
        .navigationTitle("Bot marketplace")
        .task {
            _ = await repo.refreshMarketplace()
            for await rows in repo.marketplace { items = rows }
        }
    }
}

// MARK: Search --------------------------------------------------------

public struct SearchScreen: View {
    private let repo: SearchRepository
    @State private var query = ""
    @State private var results: [MessageRecord] = []
    @State private var debounceTask: Task<Void, Never>?
    public init(repo: SearchRepository) { self.repo = repo }

    public var body: some View {
        List(results, id: \.id) { m in
            VStack(alignment: .leading, spacing: 2) {
                Text(m.senderUsername ?? "—").font(.caption).foregroundStyle(.secondary)
                Text(m.plaintext ?? "").lineLimit(2)
            }
        }
        .searchable(text: $query)
        .navigationTitle("Search")
        .onChange(of: query) { _, newValue in
            debounceTask?.cancel()
            debounceTask = Task {
                try? await Task.sleep(nanoseconds: 180_000_000)
                if Task.isCancelled { return }
                results = await repo.search(newValue, limit: 50)
            }
        }
    }
}

// MARK: Threads -------------------------------------------------------

public struct ThreadsScreen: View {
    private let repo: ThreadsRepository
    private let roomId: Int64
    @State private var items: [Thread] = []
    public init(repo: ThreadsRepository, roomId: Int64) { self.repo = repo; self.roomId = roomId }

    public var body: some View {
        List(items, id: \.id) { t in
            VStack(alignment: .leading) {
                Text(t.title).bold()
                Text("\(t.replyCount) replies").font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Threads")
        .task {
            _ = await repo.refresh(roomId)
            for await rows in repo.observeForRoom(roomId) { items = rows }
        }
    }
}

// MARK: Feeds ---------------------------------------------------------

public struct ChannelFeedsScreen: View {
    private let repo: ChannelFeedRepository
    private let roomId: Int64
    @State private var items: [ChannelFeed] = []
    @State private var showAdd = false
    @State private var newUrl = ""
    public init(repo: ChannelFeedRepository, roomId: Int64) { self.repo = repo; self.roomId = roomId }

    public var body: some View {
        List {
            ForEach(items, id: \.id) { f in
                VStack(alignment: .leading) {
                    Text(f.url)
                    Text("\(f.feedType.uppercased()) · \(f.isActive ? "active" : "paused")")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .onDelete { idxs in
                let toRemove = idxs.map { items[$0].id }
                Task { for id in toRemove { _ = await repo.unsubscribe(id) } }
            }
        }
        .navigationTitle("Channel feeds")
        .toolbar { Button("Add") { showAdd = true } }
        .task {
            _ = await repo.refresh(roomId)
            for await rows in repo.observe(roomId) { items = rows }
        }
        .alert("Add feed", isPresented: $showAdd) {
            TextField("Feed URL", text: $newUrl)
            Button("Subscribe") {
                Task { _ = await repo.subscribe(roomId: roomId, url: newUrl, feedType: "rss") }
                newUrl = ""
            }
            Button("Cancel", role: .cancel) { newUrl = "" }
        }
    }
}

// MARK: Gravitix docs -------------------------------------------------

public struct GravitixDocsScreen: View {
    private let locales: LocaleSource
    @State private var sections: [(String, String)] = []
    public init(locales: LocaleSource) { self.locales = locales }

    public var body: some View {
        List(sections, id: \.0) { kv in
            VStack(alignment: .leading) {
                Text(kv.0).font(.caption).foregroundStyle(.secondary)
                Text(kv.1)
            }
        }
        .navigationTitle("Gravitix docs")
        .task {
            let keys = [
                "gravitixDocs.title", "gravitixDocs.subtitle",
                "gravitixDocs.intro",  "gravitixDocs.introDesc",
                "gravitixDocs.designGoals",
            ]
            var loaded: [(String, String)] = []
            for k in keys { loaded.append((k, await locales.translate(k))) }
            sections = loaded
        }
    }
}

// MARK: Gravitix IDE --------------------------------------------------

/// Minimal editor — monospace TextField with soft keyword highlight in
/// the placeholder comment. A proper syntax tree lands in a follow-up.
public struct IdeScreen: View {
    @State private var code: String = SAMPLE

    public init() {}

    public var body: some View {
        TextEditor(text: $code)
            .font(.system(size: 13, design: .monospaced))
            .foregroundStyle(Color(red: 0xEE/255, green: 0xEE/255, blue: 0xF2/255))
            .scrollContentBackground(.hidden)
            .background(Color(red: 0x0A/255, green: 0x0A/255, blue: 0x14/255).ignoresSafeArea())
            .navigationTitle("Gravitix IDE")
    }

    private static let SAMPLE = """
    // Gravitix sample — counter bot
    state counter: int = 0

    handler /start {
        emit "Hello from Vortex!"
    }

    handler /inc {
        counter = counter + 1
        emit "count = " + counter
    }
    """
}
