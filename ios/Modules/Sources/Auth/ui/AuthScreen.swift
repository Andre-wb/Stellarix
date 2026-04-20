import SwiftUI

/// Wave 5 auth screen — login / register toggle + submit.
/// VM depends on [AuthRepository] only; Wave 6's identity generation
/// plugs into a post-login hook in AppEnvironment, not here.
@MainActor
public final class AuthViewModel: ObservableObject {
    public enum Mode { case login, register }
    public enum UiEvent: Equatable {
        case idle, submitting, error(String), loggedIn
    }

    @Published public private(set) var event: UiEvent = .idle

    private let repo: AuthRepository

    public init(repo: AuthRepository) { self.repo = repo }

    public func submit(mode: Mode, username: String, password: String) async {
        event = .submitting
        let pw = Data(password.utf8)
        let result: AuthResult = switch mode {
        case .login:    await repo.login(username: username.trimmingCharacters(in: .whitespaces), password: pw)
        case .register: await repo.register(username: username.trimmingCharacters(in: .whitespaces), password: pw)
        }
        event = switch result {
        case .ok: .loggedIn
        case .error(_, let message): .error(message)
        }
    }
}

public struct AuthScreen: View {
    @StateObject private var vm: AuthViewModel
    @State private var mode: AuthViewModel.Mode = .login
    @State private var username = ""
    @State private var password = ""
    private let onLoggedIn: () -> Void

    public init(repo: AuthRepository, onLoggedIn: @escaping () -> Void) {
        _vm = StateObject(wrappedValue: AuthViewModel(repo: repo))
        self.onLoggedIn = onLoggedIn
    }

    public var body: some View {
        ZStack {
            Color(red: 0x07/255, green: 0x07/255, blue: 0x0E/255).ignoresSafeArea()
            VStack(spacing: 16) {
                Text(mode == .login ? "Sign in" : "Create account")
                    .font(.largeTitle.bold())
                    .foregroundStyle(.white)
                TextField("Username", text: $username)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                SecureField("Password", text: $password)
                    .textFieldStyle(.roundedBorder)
                Button(mode == .login ? "Sign in" : "Register") {
                    Task { await vm.submit(mode: mode, username: username, password: password) }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255))
                .disabled(username.isEmpty || password.isEmpty || vm.event == .submitting)

                Button(mode == .login ? "No account? Register" : "Already registered? Sign in") {
                    mode = (mode == .login) ? .register : .login
                }
                .font(.footnote)
                .tint(.white.opacity(0.6))

                if case .error(let msg) = vm.event {
                    Text(msg).font(.footnote).foregroundStyle(.red).multilineTextAlignment(.center)
                }
            }
            .padding(24)
        }
        .onChange(of: vm.event) { _, new in
            if new == .loggedIn { onLoggedIn() }
        }
        .preferredColorScheme(.dark)
    }
}
