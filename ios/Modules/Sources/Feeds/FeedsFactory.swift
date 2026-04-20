import Foundation
import Net
import DB

public struct FeedsFactory {
    public let repo: ChannelFeedRepository
    public init(http: HttpClient, db: DBFactory) {
        self.repo = HttpChannelFeedRepository(http: http, dao: db.feeds)
    }
}
