import SwiftUI
import DB
import Rooms
import Folders

/// Primary post-auth screen — sidebar with rooms + "+" to create/join.
/// Top-left menu opens the drawer for Spaces / Bots / Search / Settings.
@MainActor
public final class RoomsListViewModel: ObservableObject {
    @Published public private(set) var rooms: [RoomRecord] = []
    @Published public private(set) var refreshing: Bool = false
    @Published public var error: String?

    private let repo: RoomsRepository
    private var observer: Task<Void, Never>?

    public init(repo: RoomsRepository) { self.repo = repo }

    public func start() {
        observer?.cancel()
        observer = Task {
            for await rows in repo.observe() {
                await MainActor.run { self.rooms = rows }
            }
        }
        Task { await refresh() }
    }
    public func stop() { observer?.cancel(); observer = nil }

    public func refresh() async {
        refreshing = true
        _ = await repo.refresh()
        refreshing = false
    }

    public func create(name: String, isPrivate: Bool) async -> Int64? {
        switch await repo.create(name: name, isPrivate: isPrivate) {
        case .ok(let id):                   return id
        case .error(_, let m): error = m;   return nil
        }
    }

    public func join(code: String) async -> Int64? {
        switch await repo.joinByInvite(code) {
        case .ok(let id):                   return id
        case .error(_, let m): error = m;   return nil
        }
    }
}

public struct RoomsListScreen: View {
    @StateObject private var vm: RoomsListViewModel
    @EnvironmentObject private var router: Router
    @State private var showCreate = false
    @State private var showJoin = false
    @State private var showDrawer = false
    @State private var selectedFolder: String = "all"
    @State private var folderList: [ChatFolder] = []
    @State private var archivedIds: Set<Int64> = []
    private let folders: Folders

    public init(repo: RoomsRepository, folders: Folders) {
        _vm = StateObject(wrappedValue: RoomsListViewModel(repo: repo))
        self.folders = folders
    }

    private var visibleRooms: [RoomRecord] {
        switch selectedFolder {
        case "all":      return vm.rooms.filter { !archivedIds.contains($0.id) }
        case "archived": return vm.rooms.filter { archivedIds.contains($0.id) }
        default:
            let ids = folderList.first(where: { $0.id == selectedFolder })?.roomIds ?? []
            return vm.rooms.filter { ids.contains($0.id) }
        }
    }

    public var body: some View {
        ZStack {
            Color(red: 0x07/255, green: 0x07/255, blue: 0x0E/255).ignoresSafeArea()
            VStack(spacing: 0) {
                FolderChips(folders: folderList,
                            selected: selectedFolder,
                            onSelect: { selectedFolder = $0 })
                List(visibleRooms, id: \.id) { room in
                    Button {
                        router.push(.chat(roomId: room.id))
                    } label: {
                        RoomRow(room: room, archived: archivedIds.contains(room.id))
                    }
                    .listRowBackground(Color.clear)
                    .listRowSeparatorTint(.white.opacity(0.08))
                    .swipeActions(edge: .trailing) {
                        let isArch = archivedIds.contains(room.id)
                        Button {
                            if isArch { folders.unarchive(roomId: room.id) }
                            else      { folders.archive(roomId: room.id) }
                            archivedIds = folders.archived()
                            folderList  = folders.list()
                        } label: {
                            Label(isArch ? "Unarchive" : "Archive",
                                  systemImage: isArch ? "tray.and.arrow.up" : "archivebox")
                        }
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
            }
        }
        .task {
            folderList = folders.list()
            archivedIds = folders.archived()
        }
        .navigationTitle("VORTEX")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .navigation) {
                Button { showDrawer = true } label: { Image(systemName: "line.3.horizontal") }
            }
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    Button("Search")      { router.push(.search) }
                    Button("New room")    { showCreate = true }
                    Button("Join room")   { showJoin = true }
                    Button("Settings")    { router.push(.settings) }
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .refreshable { await vm.refresh() }
        .onAppear { vm.start() }
        .onDisappear { vm.stop() }
        .sheet(isPresented: $showCreate) {
            CreateRoomSheet { name, isPrivate in
                Task {
                    if let id = await vm.create(name: name, isPrivate: isPrivate) {
                        showCreate = false
                        router.push(.chat(roomId: id))
                    }
                }
            }
        }
        .sheet(isPresented: $showJoin) {
            JoinRoomSheet { code in
                Task {
                    if let id = await vm.join(code: code) {
                        showJoin = false
                        router.push(.chat(roomId: id))
                    }
                }
            }
        }
        .sheet(isPresented: $showDrawer) {
            NavigationStack {
                List {
                    Button("Spaces")           { showDrawer = false; router.push(.spaces)  }
                    Button("Bot marketplace")  { showDrawer = false; router.push(.bots)    }
                    Button("Search")           { showDrawer = false; router.push(.search)  }
                    Button("Gravitix docs")    { showDrawer = false; router.push(.docs)    }
                    Button("Gravitix IDE")     { showDrawer = false; router.push(.ide)     }
                    Button("Contacts")         { showDrawer = false; router.push(.contacts) }
                    Button("Premium")          { showDrawer = false; router.push(.premium)  }
                    Divider()
                    Button("Settings")         { showDrawer = false; router.push(.settings) }
                }
                .navigationTitle("Menu")
            }
            .presentationDetents([.medium])
        }
    }
}

private struct RoomRow: View {
    let room: RoomRecord
    let archived: Bool
    var body: some View {
        HStack(spacing: 12) {
            Text(room.avatarEmoji).font(.title2)
            VStack(alignment: .leading, spacing: 2) {
                Text(room.name).foregroundStyle(.white)
                Text("\(archived ? "archived · " : "")\(room.memberCount) members\(room.isChannel ? " · channel" : "")")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.5))
            }
            Spacer()
            if room.unreadCount > 0 {
                Text("\(room.unreadCount)")
                    .font(.caption.bold())
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255),
                                in: Capsule())
                    .foregroundStyle(.white)
            }
        }
        .padding(.vertical, 6)
    }
}

private struct FolderChips: View {
    let folders: [ChatFolder]
    let selected: String
    let onSelect: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(folders, id: \.id) { f in
                    Button { onSelect(f.id) } label: {
                        Text(f.title)
                            .font(.footnote)
                            .padding(.horizontal, 12).padding(.vertical, 6)
                            .background(
                                Capsule().fill(
                                    f.id == selected
                                        ? Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255)
                                        : Color.white.opacity(0.08)
                                )
                            )
                            .foregroundStyle(.white)
                    }
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
        }
    }
}

private struct CreateRoomSheet: View {
    var onCreate: (String, Bool) -> Void
    @State private var name = ""
    @State private var isPrivate = false
    var body: some View {
        NavigationStack {
            Form {
                #if canImport(UIKit)
                TextField("Room name", text: $name).textInputAutocapitalization(.words)
                #else
                TextField("Room name", text: $name)
                #endif
                Toggle("Private", isOn: $isPrivate)
            }
            .navigationTitle("New room")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") { onCreate(name, isPrivate) }.disabled(name.isEmpty)
                }
            }
        }
    }
}

private struct JoinRoomSheet: View {
    var onJoin: (String) -> Void
    @State private var code = ""
    var body: some View {
        NavigationStack {
            Form {
                TextField("Invite code", text: $code)
                    #if canImport(UIKit)
                    .textInputAutocapitalization(.never)
                    #endif
                    .autocorrectionDisabled()
            }
            .navigationTitle("Join room")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Join") { onJoin(code) }.disabled(code.isEmpty)
                }
            }
        }
    }
}
