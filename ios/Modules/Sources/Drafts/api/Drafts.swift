import Foundation

/// Per-room message drafts. Persisted to the backend via
/// PUT/DELETE /api/rooms/{id}/draft and mirrored locally so the chat
/// composer can pre-fill on open without waiting for a round-trip.
public protocol Drafts: Sendable {
    /// Latest known draft for [roomId], or nil if none.
    func get(roomId: Int64) async -> String?

    /// Replace the draft. Empty string is treated as "clear".
    func set(roomId: Int64, text: String) async

    /// Remove the draft for [roomId].
    func clear(roomId: Int64) async
}
