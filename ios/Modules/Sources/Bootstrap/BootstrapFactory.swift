import Foundation

/// Composition helper for the Bootstrap feature.
///
/// Keeps construction of the default stack in one place so `AppEnvironment`
/// doesn't have to know about every impl class.
public struct BootstrapFactory {
    public let directory: NodeDirectory
    public let prefs: NodePreferences

    public init(
        directory: NodeDirectory = URLSessionNodeDirectory(),
        prefs: NodePreferences  = UserDefaultsNodePreferences(),
    ) {
        self.directory = directory
        self.prefs = prefs
    }
}
