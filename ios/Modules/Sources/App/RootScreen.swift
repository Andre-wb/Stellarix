import SwiftUI
import Bootstrap
import Auth
import Chat
import Calls
import Files

/// Top-level navigation gate.
///
/// `NavigationStack` is rooted at the rooms list once bootstrap + auth
/// are cleared. The `Router` publishes typed routes so each destination
/// stays a pure function of its Route value — restorable, deep-linkable.
public struct RootScreen: View {
    @State private var baseUrl: String?
    @State private var session: Session = .loggedOut
    @StateObject private var router = Router()
    private let env: AppEnvironment

    public init(env: AppEnvironment = .shared) {
        self.env = env
        _baseUrl = State(initialValue: env.bootstrap.prefs.currentBaseUrl())
        _session = State(initialValue: env.auth.repo.currentSession())
    }

    public var body: some View {
        Group {
            if baseUrl == nil {
                BootstrapScreen(
                    directory: env.bootstrap.directory,
                    prefs: env.bootstrap.prefs,
                    onConnected: { baseUrl = $0 },
                )
            } else if session == .loggedOut {
                AuthScreen(repo: env.auth.repo, onLoggedIn: {
                    session = env.auth.repo.currentSession()
                })
            } else {
                mainNav
            }
        }
        .task {
            for await s in env.auth.repo.session { session = s }
        }
        .preferredColorScheme(.dark)
    }

    private var mainNav: some View {
        NavigationStack(path: $router.path) {
            RoomsListScreen(repo: env.rooms.repo)
                .navigationDestination(for: Route.self, destination: destination(for:))
        }
        .environmentObject(router)
        .task {
            // Start the WebSocket once we're logged in so signalling
            // (chat + calls) is ready the moment the user opens a room.
            await env.ws.client.start()
        }
    }

    @ViewBuilder
    private func destination(for route: Route) -> some View {
        switch route {
        case .chat(let roomId):
            ChatScreen(
                roomId: roomId,
                sender: env.chat.sender,
                incoming: env.chat.incoming,
                actions: env.chat.actions,
                onOpenThread: { thread in
                    // Server treats a thread as a pseudo-room — reuse
                    // the chat UI at the thread's own id.
                    router.push(.chat(roomId: thread.id))
                },
            )
        case .call(let roomId, let video):
            CallScreen(controller: env.calls.controller,
                       roomId: roomId, initialVideo: video,
                       onExit: { router.pop() })
        case .settings:
            SettingsScreen(store: env.settings.store,
                           identity: env.identity.repo,
                           auth: env.auth.repo)
        case .spaces:       SpacesScreen(repo: env.spaces.repo)
        case .bots:         BotsScreen(repo: env.bots.repo)
        case .search:       SearchScreen(repo: env.search.repo)
        case .docs:         GravitixDocsScreen(locales: env.i18n.locales)
        case .ide:          IdeScreen()
        case .threads(let id): ThreadsScreen(repo: env.threads.repo, roomId: id)
        case .feeds(let id):   ChannelFeedsScreen(repo: env.feeds.repo, roomId: id)
        }
    }
}
