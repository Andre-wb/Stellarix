import Foundation

/// [NodePreferences] over `UserDefaults.standard`. Lives under App Group's
/// default domain so the NotificationService extension (Wave 18) can
/// read the base URL without re-parsing a JWT first.
///
/// Observers subscribe via an `AsyncStream` bridge over KVO so there's
/// no dependency on Combine in this module.
public final class UserDefaultsNodePreferences: NodePreferences {
    private let defaults: UserDefaults
    private let key = "vortex.baseUrl"
    private let continuations = Continuations()

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    public var baseUrlStream: AsyncStream<String?> {
        AsyncStream { cont in
            // Emit current immediately so downstream collectors get seeded.
            cont.yield(self.defaults.string(forKey: self.key))
            let id = UUID()
            self.continuations.add(cont, for: id)
            cont.onTermination = { @Sendable _ in self.continuations.remove(id) }
        }
    }

    public func currentBaseUrl() -> String? { defaults.string(forKey: key) }

    public func setBaseUrl(_ url: String?) {
        if let url, !url.isEmpty {
            defaults.set(url, forKey: key)
        } else {
            defaults.removeObject(forKey: key)
        }
        continuations.yield(url)
    }

    /// Thread-safe registry of live `AsyncStream` continuations.
    /// A plain dictionary + a lock is enough — we never have more than a
    /// handful of observers (one per ViewModel).
    private final class Continuations: @unchecked Sendable {
        private let lock = NSLock()
        private var map: [UUID: AsyncStream<String?>.Continuation] = [:]

        func add(_ c: AsyncStream<String?>.Continuation, for id: UUID) {
            lock.lock(); defer { lock.unlock() }
            map[id] = c
        }
        func remove(_ id: UUID) {
            lock.lock(); defer { lock.unlock() }
            map.removeValue(forKey: id)
        }
        func yield(_ v: String?) {
            lock.lock(); let copy = map.values; lock.unlock()
            for c in copy { c.yield(v) }
        }
    }
}
