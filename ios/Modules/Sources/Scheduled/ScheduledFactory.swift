import Foundation
import Net

public struct ScheduledFactory {
    public let scheduled: ScheduledMessages
    public init(http: HttpClient) { self.scheduled = HttpScheduled(http: http) }
}
