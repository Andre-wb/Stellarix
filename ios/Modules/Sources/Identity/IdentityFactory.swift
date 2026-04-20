import Foundation
import VortexCrypto
import Auth

public struct IdentityFactory {
    public let seeds: SeedProvider
    public let repo: IdentityRepository

    public init(crypto: VortexCryptoFactory, store: SecureStore) throws {
        let seeds = try Bip39SeedProvider(random: crypto.random)
        self.seeds = seeds
        self.repo = SeedIdentityRepository(seeds: seeds, kdf: crypto.kdf, store: store)
    }
}
