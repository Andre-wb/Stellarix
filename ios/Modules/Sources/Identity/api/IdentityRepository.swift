import Foundation
import VortexCrypto

/// User cryptographic identity — lives on this device only, derived
/// from the seed phrase. Both key pairs are always present together —
/// a half-initialised state is a bug, not a feature.
public protocol IdentityRepository: AnyObject, Sendable {
    var current: Identity? { get }
    func createOrLoad() async throws -> Identity
    func wipe()
}

public struct Identity: Equatable, Sendable {
    public let mnemonic: Mnemonic
    public let x25519: KeyPair
    public let ed25519: KeyPair
    public init(mnemonic: Mnemonic, x25519: KeyPair, ed25519: KeyPair) {
        self.mnemonic = mnemonic
        self.x25519 = x25519
        self.ed25519 = ed25519
    }
}
