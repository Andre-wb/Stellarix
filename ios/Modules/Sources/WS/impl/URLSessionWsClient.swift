import Foundation
import Net

/// URLSession-backed WebSocket with exponential backoff reconnect.
/// Bearer auth flows through the same `AuthTokenSource` the HTTP client
/// uses; no separate login.
public actor URLSessionWsClient: WsClient {
    private let base: BaseUrlProvider
    private let tokens: AuthTokenSource
    private let session: URLSession
    private var task: URLSessionWebSocketTask?
    private var runner: Task<Void, Never>?
    private let stateBridge = Bridge<WsState>(initial: .disconnected)
    private let incomingBridge = Bridge<String>(initial: nil)

    public nonisolated var state: AsyncStream<WsState>  { stateBridge.stream() }
    public nonisolated var incoming: AsyncStream<String> { incomingBridge.stream() }

    public init(base: BaseUrlProvider, tokens: AuthTokenSource) {
        self.base = base
        self.tokens = tokens
        let cfg = URLSessionConfiguration.default
        cfg.shouldUseExtendedBackgroundIdleMode = true
        self.session = URLSession(configuration: cfg)
    }

    public func start() async {
        if runner != nil { return }
        runner = Task { [weak self] in await self?.loop() }
    }

    public func stop() async {
        runner?.cancel(); runner = nil
        task?.cancel(with: .goingAway, reason: nil); task = nil
        stateBridge.publish(.disconnected)
    }

    public func send(_ text: String) async {
        guard let task else { return }
        do { try await task.send(.string(text)) }
        catch { /* dropped — reconnect loop will recover */ }
    }

    // ── internals ──────────────────────────────────────────────────────

    private func loop() async {
        let backoff: [UInt64] = [500_000_000, 1_000_000_000, 2_000_000_000, 5_000_000_000, 10_000_000_000]
        var attempt = 0
        while !Task.isCancelled {
            stateBridge.publish(.connecting)
            guard await connectOnce() else {
                let wait = backoff[min(attempt, backoff.count - 1)]
                attempt += 1
                stateBridge.publish(.failed(reason: "connect_fail"))
                try? await Task.sleep(nanoseconds: wait)
                continue
            }
            attempt = 0
            stateBridge.publish(.connected)
            await pump()
            stateBridge.publish(.disconnected)
            try? await Task.sleep(nanoseconds: backoff[0])
        }
    }

    private func connectOnce() async -> Bool {
        guard var baseUrl = base.current(), !baseUrl.isEmpty else { return false }
        while baseUrl.hasSuffix("/") { baseUrl.removeLast() }
        let wsUrl = baseUrl
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        guard let url = URL(string: "\(wsUrl)/ws") else { return false }
        var req = URLRequest(url: url)
        if let token = await tokens.accessToken(), !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        self.task = session.webSocketTask(with: req)
        task?.resume()
        return true
    }

    private func pump() async {
        guard let task else { return }
        while !Task.isCancelled {
            do {
                let frame = try await task.receive()
                if case .string(let s) = frame { incomingBridge.publish(s) }
            } catch {
                break
            }
        }
    }
}

/// Thread-safe one-value fan-out across AsyncStream consumers.
/// `initial == nil` means subscribers get only values published after
/// they subscribe (suitable for an event bus like incoming frames).
private final class Bridge<Value: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var subs: [UUID: AsyncStream<Value>.Continuation] = [:]
    private var last: Value?

    init(initial: Value?) { self.last = initial }

    func publish(_ v: Value) {
        lock.lock()
        last = v
        let copy = subs.values
        lock.unlock()
        for c in copy { c.yield(v) }
    }

    func stream() -> AsyncStream<Value> {
        AsyncStream { cont in
            lock.lock()
            if let last { cont.yield(last) }
            let id = UUID(); subs[id] = cont
            lock.unlock()
            cont.onTermination = { @Sendable _ in
                self.lock.lock(); self.subs.removeValue(forKey: id); self.lock.unlock()
            }
        }
    }
}
