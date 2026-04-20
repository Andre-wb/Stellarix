import Foundation
import Net

public struct FederationFactory {
    public let directory: MirrorDirectory
    public init(http: HttpClient) { self.directory = HttpMirrorDirectory(http: http) }
}
