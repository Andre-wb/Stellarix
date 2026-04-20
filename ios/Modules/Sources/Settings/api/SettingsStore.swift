import Foundation

public protocol SettingsStore: Sendable {
    var theme: AsyncStream<String> { get }               // "system" | "dark" | "light"
    var notificationsEnabled: AsyncStream<Bool> { get }
    func setTheme(_ mode: String) async
    func setNotificationsEnabled(_ on: Bool) async
    func wipeAll() async
}
