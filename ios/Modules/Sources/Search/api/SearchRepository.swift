import Foundation
import DB

public protocol SearchRepository: Sendable {
    /// FTS-style query: prefix match with `*`, AND/OR, `"quoted phrase"`.
    func search(_ query: String, limit: Int) async -> [MessageRecord]
    func index(id: Int64, plaintext: String) async
    func unindex(_ id: Int64) async
}
