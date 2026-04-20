import Foundation
import DB
import Identity
import Auth

/// [SettingsStore] backed by UserDefaults + DB wipe on panic.
public final class UserDefaultsSettingsStore: SettingsStore {
    private let defaults: UserDefaults
    private let db: DBFactory
    private let identity: IdentityRepository
    private let auth: AuthRepository
    private let themeBridge = Bridge<String>(initial: "system")
    private let notifBridge = Bridge<Bool>(initial: true)

    public init(defaults: UserDefaults = .standard,
                db: DBFactory,
                identity: IdentityRepository,
                auth: AuthRepository) {
        self.defaults = defaults
        self.db = db
        self.identity = identity
        self.auth = auth
        themeBridge.publish(defaults.string(forKey: "theme") ?? "system")
        notifBridge.publish(defaults.object(forKey: "notifs") as? Bool ?? true)
    }

    public var theme: AsyncStream<String> { themeBridge.stream() }
    public var notificationsEnabled: AsyncStream<Bool> { notifBridge.stream() }

    public func setTheme(_ mode: String) async {
        defaults.set(mode, forKey: "theme"); themeBridge.publish(mode)
    }
    public func setNotificationsEnabled(_ on: Bool) async {
        defaults.set(on, forKey: "notifs"); notifBridge.publish(on)
    }

    public func wipeAll() async {
        // Clear settings, identity and session. DB wipe is best-effort —
        // GRDB's destructive drop happens by truncating each table.
        defaults.removeObject(forKey: "theme")
        defaults.removeObject(forKey: "notifs")
        identity.wipe()
        await auth.logout()
        try? await db.db.pool.write { database in
            for table in ["rooms", "messages", "room_keys", "spaces", "bots",
                          "threads", "channel_feeds", "reactions", "read_receipts"] {
                try database.execute(sql: "DELETE FROM \(table)")
            }
            try database.execute(sql: "DELETE FROM messages_fts")
        }
    }

    private final class Bridge<V: Sendable>: @unchecked Sendable {
        private let lock = NSLock()
        private var subs: [UUID: AsyncStream<V>.Continuation] = [:]
        private var last: V
        init(initial: V) { self.last = initial }
        func publish(_ v: V) {
            lock.lock(); last = v; let copy = subs.values; lock.unlock()
            for c in copy { c.yield(v) }
        }
        func stream() -> AsyncStream<V> {
            AsyncStream { cont in
                lock.lock(); cont.yield(last); let id = UUID(); subs[id] = cont; lock.unlock()
                cont.onTermination = { @Sendable _ in
                    self.lock.lock(); self.subs.removeValue(forKey: id); self.lock.unlock()
                }
            }
        }
    }
}
