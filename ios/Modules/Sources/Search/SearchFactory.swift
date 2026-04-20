import Foundation
import DB

public struct SearchFactory {
    public let repo: SearchRepository
    public init(db: DBFactory) {
        self.repo = Fts5SearchRepository(dao: db.search)
    }
}
