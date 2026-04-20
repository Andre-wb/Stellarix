import Foundation
import Net
import DB

public struct SpacesFactory {
    public let repo: SpacesRepository
    public init(http: HttpClient, db: DBFactory) {
        self.repo = HttpSpacesRepository(http: http, dao: db.spaces)
    }
}
