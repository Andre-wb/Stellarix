import Foundation

/// 24-word BIP39 mnemonic source.
///
/// Split from [IdentityRepository] so:
///   - Wave 6 only generates; Wave 20 adds import/restore without changing
///     consumers.
///   - Tests can deterministically inject a known mnemonic.
public protocol SeedProvider: Sendable {
    func generate() throws -> Mnemonic
    func toSeed(mnemonic: Mnemonic, passphrase: Data) throws -> Data
}

public extension SeedProvider {
    func toSeed(mnemonic: Mnemonic) throws -> Data { try toSeed(mnemonic: mnemonic, passphrase: Data()) }
}

public struct Mnemonic: Equatable, Sendable {
    public let words: [String]
    public init(words: [String]) throws {
        guard words.count == 24 else { throw SeedError.badWordCount(words.count) }
        self.words = words
    }
    public var phrase: String { words.joined(separator: " ") }
}

public enum SeedError: Error, Equatable {
    case badWordCount(Int)
    case wordlistUnavailable
    case unknownWord(String)
}
