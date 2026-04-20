import Foundation
import Security

/// SecItem-backed [SecureStore] using `kSecClassGenericPassword` with
/// `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` — the user must
/// have unlocked the device once since boot, and the blob never leaves
/// this device (no iCloud Keychain sync).
public final class KeychainSecureStore: SecureStore {
    private let service: String

    public init(service: String = "sol.vortexx.app") { self.service = service }

    public func getString(_ key: String) -> String? {
        var query = baseQuery(key)
        query[kSecReturnData as String]  = true
        query[kSecMatchLimit as String]  = kSecMatchLimitOne
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public func setString(_ key: String, _ value: String?) {
        let q = baseQuery(key)
        if let value, let data = value.data(using: .utf8) {
            let attrs: [String: Any] = [
                kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            ]
            let status = SecItemUpdate(q as CFDictionary, attrs as CFDictionary)
            if status == errSecItemNotFound {
                var insert = q
                insert.merge(attrs) { _, new in new }
                SecItemAdd(insert as CFDictionary, nil)
            }
        } else {
            SecItemDelete(q as CFDictionary)
        }
    }

    public func clear() {
        let q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
        ]
        SecItemDelete(q as CFDictionary)
    }

    private func baseQuery(_ key: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
    }
}
