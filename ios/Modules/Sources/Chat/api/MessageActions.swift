import Foundation
import Threads

/// Wave 13 surface: reactions, edits, replies, threads, delete.
public protocol MessageActions: Sendable {
    func react(messageId: Int64, emoji: String) async -> Bool
    func edit(messageId: Int64, newPlaintext: String) async -> Bool
    func reply(roomId: Int64, replyToMessageId: Int64, plaintext: String) async -> SendOutcome
    func delete(messageId: Int64) async -> Bool

    /// Spin up a real thread rooted at [messageId]. Returns the created
    /// [Thread] so the caller can navigate into it; nil on error (no
    /// such message / network failure). Title falls back to the first
    /// 40 characters of the parent message's plaintext.
    func openThread(messageId: Int64, title: String?) async -> Threads.Thread?
}
