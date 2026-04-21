import Foundation
import Net
import Auth

public struct AccountsFactory {
    public let manager: AccountsManager
    public init(store: SecureStore,
                http: @escaping (String) -> HttpClient,
                onActiveChanged: @escaping (SavedAccount, String) -> Void) {
        self.manager = KeychainAccountsManager(
            store: store, http: http, onActiveChanged: onActiveChanged,
        )
    }
}
