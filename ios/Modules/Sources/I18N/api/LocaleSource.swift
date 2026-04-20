import Foundation

public protocol LocaleSource: Sendable {
    var current: AsyncStream<String> { get }
    func setLocale(_ code: String) async
    func translate(_ key: String) async -> String
}
