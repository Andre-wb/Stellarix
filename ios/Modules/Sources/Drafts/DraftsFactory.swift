import Foundation
import Net

public struct DraftsFactory {
    public let drafts: Drafts
    public init(http: HttpClient) { self.drafts = HttpDrafts(http: http) }
}
