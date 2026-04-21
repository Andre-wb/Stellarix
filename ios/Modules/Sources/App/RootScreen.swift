import SwiftUI
import Bootstrap
import Auth
import Chat
import Calls
import Files
import Emoji
import Folders
import Contacts
import Premium
import I18N

/// Top-level navigation gate.
///
/// `NavigationStack` is rooted at the rooms list once bootstrap + auth
/// are cleared. The `Router` publishes typed routes so each destination
/// stays a pure function of its Route value — restorable, deep-linkable.
public struct RootScreen: View {
    @State private var baseUrl: String?
    @State private var session: Session = .loggedOut
    @State private var languagePicked: Bool
    @StateObject private var router = Router()
    private let env: AppEnvironment

    public init(env: AppEnvironment = .shared) {
        self.env = env
        // Dev helper: if the scheme sets VORTEX_RESET_FIRST_RUN=1,
        // wipe the language flag + saved base URL + auth tokens so the
        // whole onboarding pipeline replays on every ⌘R. Prod builds
        // just skip this — env var is never set in App Store runs.
        if ProcessInfo.processInfo.environment["VORTEX_RESET_FIRST_RUN"] == "1" {
            RootScreen.resetFirstRun(env: env)
        }
        _baseUrl = State(initialValue: env.bootstrap.prefs.currentBaseUrl())
        _session = State(initialValue: env.auth.repo.currentSession())
        _languagePicked = State(
            initialValue: UserDefaults.standard.bool(forKey: "vortex.language.picked"),
        )
    }

    /// Clear all onboarding state so the language + mode pickers show
    /// again on next render. Wired to the env flag above and to the
    /// hidden triple-tap on the VORTEX wordmark exposed in first-run
    /// screens via [resetOnboarding].
    public static func resetFirstRun(env: AppEnvironment) {
        UserDefaults.standard.removeObject(forKey: "vortex.language.picked")
        UserDefaults.standard.removeObject(forKey: "locale")
        env.bootstrap.prefs.setBaseUrl(nil)
        Task { await env.auth.repo.logout() }
    }

    private func resetOnboarding() {
        Self.resetFirstRun(env: env)
        languagePicked = false
        baseUrl = nil
        session = .loggedOut
    }

    public var body: some View {
        Group {
            if !languagePicked {
                LanguageSelectScreen(
                    locales: env.i18n.locales,
                    preselected: UserDefaults.standard.string(forKey: "locale") ?? "en",
                    onContinue: { code in
                        env.i18n.localizer.setLocale(code)
                        languagePicked = true
                    },
                )
                .overlay(alignment: .topTrailing) { resetHotspot }
            } else if baseUrl == nil {
                BootstrapScreen(
                    directory: env.bootstrap.directory,
                    prefs: env.bootstrap.prefs,
                    onConnected: { baseUrl = $0 },
                )
                .overlay(alignment: .topTrailing) { resetHotspot }
            } else if session == .loggedOut {
                AuthScreen(repo: env.auth.repo, onLoggedIn: {
                    session = env.auth.repo.currentSession()
                })
                .overlay(alignment: .topTrailing) { resetHotspot }
            } else {
                mainNav
            }
        }
        .environmentObject(env.i18n.localizer)
        .task {
            for await s in env.auth.repo.session { session = s }
        }
        .preferredColorScheme(.dark)
    }

    /// 56×56 invisible hit-target in the top-right corner. Triple-tap
    /// while onboarding replays the whole language → bootstrap → auth
    /// flow. Reachable from iPhone one-hand use; production users will
    /// almost never discover it.
    private var resetHotspot: some View {
        Color.clear
            .frame(width: 56, height: 56)
            .contentShape(Rectangle())
            .onTapGesture(count: 3) { resetOnboarding() }
    }

    private var mainNav: some View {
        NavigationStack(path: $router.path) {
            RoomsListScreen(repo: env.rooms.repo, folders: env.folders.folders)
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
                emojiCatalog: env.emoji.catalog,
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
        case .contacts:        ContactsScreen(repo: env.contacts.contacts,
                                              onOpenDm: { _ in router.pop() })
        case .premium:         PremiumScreen(repo: env.premium.premium)
        }
    }
}
