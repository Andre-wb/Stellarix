import Foundation

/// Value types for keys + Argon2 parameters. Kept as plain `Data` + structs
/// so interop with hex-encoded wire formats is direct — no bridging layer
/// between network DTOs and crypto calls.
public struct KeyPair: Equatable, Sendable {
    public let privateKey: Data
    public let publicKey: Data

    public init(privateKey: Data, publicKey: Data) {
        self.privateKey = privateKey
        self.publicKey  = publicKey
    }
}

/// OWASP 2024 defaults for interactive logins (≈150 ms on a recent iPhone).
/// Use `.sensitive()` for key-derivation from a seed phrase.
public struct Argon2Params: Equatable, Sendable {
    public let iterations: Int
    public let memoryKiB: Int
    public let parallelism: Int
    public let hashLen: Int

    public init(iterations: Int, memoryKiB: Int, parallelism: Int, hashLen: Int) {
        self.iterations = iterations
        self.memoryKiB = memoryKiB
        self.parallelism = parallelism
        self.hashLen = hashLen
    }

    public static func interactive() -> Argon2Params {
        .init(iterations: 3, memoryKiB: 65_536, parallelism: 1, hashLen: 32)
    }

    public static func sensitive() -> Argon2Params {
        .init(iterations: 4, memoryKiB: 131_072, parallelism: 1, hashLen: 32)
    }
}
