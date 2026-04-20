import Foundation
import DB

/// FTS5-backed search over decrypted message plaintext cached locally.
public final class Fts5SearchRepository: SearchRepository {
    private let dao: SearchDao

    public init(dao: SearchDao) { self.dao = dao }

    public func search(_ query: String, limit: Int) async -> [MessageRecord] {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return [] }
        // Prefix search unless the user already typed an operator / quote.
        let fts = (q.contains(" ") || q.hasSuffix("*") || q.hasPrefix("\"")) ? q : "\(q)*"
        return (try? await dao.search(fts, limit: limit)) ?? []
    }

    public func index(id: Int64, plaintext: String) async {
        try? await dao.index(id: id, plaintext: plaintext)
    }

    public func unindex(_ id: Int64) async {
        try? await dao.unindex(id)
    }
}
