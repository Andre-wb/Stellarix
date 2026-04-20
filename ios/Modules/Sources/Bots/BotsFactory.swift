import Foundation
import Net
import DB

public struct BotsFactory {
    public let repo: BotsRepository
    public init(http: HttpClient, db: DBFactory) {
        self.repo = HttpBotsRepository(http: http, dao: db.bots)
    }
}
