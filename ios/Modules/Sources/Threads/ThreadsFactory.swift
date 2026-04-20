import Foundation
import Net
import DB

public struct ThreadsFactory {
    public let repo: ThreadsRepository
    public init(http: HttpClient, db: DBFactory) {
        self.repo = HttpThreadsRepository(http: http, dao: db.threads)
    }
}
