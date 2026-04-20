import Foundation
import CryptoKit
import VortexCrypto
import Auth

/// Derives and persists the device identity.
///
/// On first call: generate mnemonic → derive 64-byte BIP39 seed → HKDF
/// split into X25519 + Ed25519 32-byte seeds → generate key pairs from
/// them → persist to Keychain via [SecureStore].
public final class SeedIdentityRepository: IdentityRepository, @unchecked Sendable {
    private let seeds: SeedProvider
    private let kdf: Kdf
    private let store: SecureStore
    private let lock = NSLock()
    private var cached: Identity?

    public init(seeds: SeedProvider, kdf: Kdf, store: SecureStore) {
        self.seeds = seeds
        self.kdf = kdf
        self.store = store
        self.cached = SeedIdentityRepository.loadFromStore(store)
    }

    public var current: Identity? {
        lock.lock(); defer { lock.unlock() }
        return cached
    }

    public func createOrLoad() async throws -> Identity {
        if let c = current { return c }
        // Consult store again — an external restore (Wave 20 key-backup
        // flow) may have populated it after wipe().
        if let fromStore = SeedIdentityRepository.loadFromStore(store) {
            lock.lock(); cached = fromStore; lock.unlock()
            return fromStore
        }
        let mnemonic = try seeds.generate()
        let seed = try seeds.toSeed(mnemonic: mnemonic)
        let id = try derive(mnemonic: mnemonic, seed: seed)
        persist(id)
        lock.lock(); cached = id; lock.unlock()
        return id
    }

    public func wipe() {
        store.setString(Keys.mnemonic,      nil)
        store.setString(Keys.x25519Priv,    nil)
        store.setString(Keys.x25519Pub,     nil)
        store.setString(Keys.ed25519Priv,   nil)
        store.setString(Keys.ed25519Pub,    nil)
        lock.lock(); cached = nil; lock.unlock()
    }

    // ── internals ──────────────────────────────────────────────────────

    private func derive(mnemonic: Mnemonic, seed: Data) throws -> Identity {
        let xSeed = try kdf.derive(ikm: seed, salt: Data(), info: Data("vortex/x25519".utf8), length: 32)
        let eSeed = try kdf.derive(ikm: seed, salt: Data(), info: Data("vortex/ed25519".utf8), length: 32)

        let xPriv = try Curve25519.KeyAgreement.PrivateKey(rawRepresentation: xSeed)
        let ePriv = try Curve25519.Signing.PrivateKey(rawRepresentation: eSeed)
        return Identity(
            mnemonic: mnemonic,
            x25519: KeyPair(privateKey: xPriv.rawRepresentation,
                            publicKey:  xPriv.publicKey.rawRepresentation),
            ed25519: KeyPair(privateKey: ePriv.rawRepresentation,
                             publicKey:  ePriv.publicKey.rawRepresentation),
        )
    }

    private func persist(_ id: Identity) {
        store.setString(Keys.mnemonic,      id.mnemonic.phrase)
        store.setString(Keys.x25519Priv,    Hex.encode(id.x25519.privateKey))
        store.setString(Keys.x25519Pub,     Hex.encode(id.x25519.publicKey))
        store.setString(Keys.ed25519Priv,   Hex.encode(id.ed25519.privateKey))
        store.setString(Keys.ed25519Pub,    Hex.encode(id.ed25519.publicKey))
    }

    private static func loadFromStore(_ s: SecureStore) -> Identity? {
        guard let phrase = s.getString(Keys.mnemonic) else { return nil }
        let parts = phrase.split(separator: " ").map(String.init)
        guard parts.count == 24,
              let xPriv = try? Hex.decode(s.getString(Keys.x25519Priv) ?? ""),
              let xPub  = try? Hex.decode(s.getString(Keys.x25519Pub)  ?? ""),
              let ePriv = try? Hex.decode(s.getString(Keys.ed25519Priv) ?? ""),
              let ePub  = try? Hex.decode(s.getString(Keys.ed25519Pub)  ?? ""),
              let m = try? Mnemonic(words: parts)
        else { return nil }
        return Identity(
            mnemonic: m,
            x25519:  KeyPair(privateKey: xPriv, publicKey: xPub),
            ed25519: KeyPair(privateKey: ePriv, publicKey: ePub),
        )
    }

    private enum Keys {
        static let mnemonic    = "id_mnemonic"
        static let x25519Priv  = "id_x25519_priv"
        static let x25519Pub   = "id_x25519_pub"
        static let ed25519Priv = "id_ed25519_priv"
        static let ed25519Pub  = "id_ed25519_pub"
    }
}
