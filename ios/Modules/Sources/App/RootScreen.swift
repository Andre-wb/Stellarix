import SwiftUI
import Bootstrap
import Auth
import VortexCrypto

/// Three-step gate: bootstrap ➜ auth ➜ home.
/// Every later wave inserts/replaces one of these branches (rooms list
/// replaces Home in Wave 8) — the gate is the single switch point.
public struct RootScreen: View {
    @State private var baseUrl: String?
    @State private var session: Session = .loggedOut
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
                    onConnected: { url in baseUrl = url },
                )
            } else if session == .loggedOut {
                AuthScreen(repo: env.auth.repo, onLoggedIn: {
                    session = env.auth.repo.currentSession()
                })
            } else {
                HomeScreen(baseUrl: baseUrl!, env: env)
            }
        }
        .task {
            // Keep the gate's `session` in sync with the repo's stream so
            // logout from Settings (Wave 20) immediately kicks us back to
            // AuthScreen — no manual observer wiring required.
            for await s in env.auth.repo.session {
                session = s
            }
        }
        .preferredColorScheme(.dark)
    }
}
