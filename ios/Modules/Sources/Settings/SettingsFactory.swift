import Foundation
import DB
import Identity
import Auth

public struct SettingsFactory {
    public let store: SettingsStore
    public init(db: DBFactory, identity: IdentityRepository, auth: AuthRepository) {
        self.store = UserDefaultsSettingsStore(db: db, identity: identity, auth: auth)
    }
}
